# api/app/auth/invitations.py
"""Invitations by mail to an institution (spec E): create, list, resend, cancel and accept.

The general admin invites an institution admin; an institution admin invites a viewer of its own institution. The
person opens the link and creates the account with a form or with Google. A pending invitation reserves a seat.

Functions flush; routers commit. The ones that can send mail return the mail: the router sends it in the background
after committing, so the response never depends on the mail server.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from radar_db.accounts import (
    AccountError,
    EmailTakenError,
    UsernameTakenError,
    create_user,
    get_user_by_email,
    normalize_email,
    normalize_full_name,
    revoke_all_sessions,
)
from radar_db.models import Invitation, Organization, User
from radar_db.passwords import PasswordPolicyError

from ..config import settings
from ..mail.service import OutgoingMail
from ..mail.templates import invitation_mail
from . import organizations, permissions
from .email_tokens import TOKEN_RE, _global_cap_reached, generate_token, hash_token
from .google import GoogleIdentity
from .google_login import GoogleLoginError, _free_username, _unusable_password

# One message for a link that is unknown, malformed, expired, used or cancelled: the answer does not tell them apart.
INVALID_LINK = "El link de la invitación no es válido o ya venció. Pedí una nueva a quien te invitó."


class InvitationError(Exception):
    """A rule of the invitations was broken; the router turns it into this HTTP status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _now(now: Optional[datetime]) -> datetime:
    """The `now` argument exists so tests can move the clock; production passes nothing."""
    return now or datetime.now(timezone.utc)


def _pending_filters(now: datetime) -> tuple:
    """SQL conditions of "pending": not accepted, not cancelled and not expired."""
    return (Invitation.accepted_at.is_(None), Invitation.cancelled_at.is_(None), Invitation.expires_at > now)


# --- sending caps ---------------------------------------------------------------------------------------------


def _check_may_send(db: Session, email: str, now: datetime) -> None:
    """429 when a mail to this address would pass a cap: MAIL_MAX_PER_HOUR to one address in the last hour,
    MAIL_MIN_INTERVAL_SECONDS between two mails to it, or the site-wide caps (which also count the account mails).

    Every invitation row counts, pending or not: cancelling and inviting again does not get around the cap."""
    recent = [
        row[0]
        for row in db.query(Invitation.created_at)
        .filter(Invitation.email == email, Invitation.created_at > now - timedelta(hours=1))
        .all()
    ]
    too_many = len(recent) >= settings.mail_max_per_hour
    too_soon = bool(recent) and max(recent) > now - timedelta(seconds=settings.mail_min_interval_seconds)
    if too_many or too_soon or _global_cap_reached(db, now, recovery=False):
        raise InvitationError(
            429, "Ya enviamos una invitación a ese mail hace poco. Esperá unos minutos y probá de nuevo"
        )


# --- creating -------------------------------------------------------------------------------------------------


def _clean_views(db: Session, role: str, radar_views: Optional[List[str]]) -> Optional[List[str]]:
    """The views an invitation carries: only for viewers, every code must be a radar (422), ["*"] means all."""
    if radar_views is None:
        return None
    if role != "viewer":
        raise InvitationError(422, "Solo un lector lleva una lista de vistas")
    try:
        return sorted(permissions._wanted_resources(db, radar_views))
    except permissions.PermissionRuleError as exc:
        raise InvitationError(exc.status_code, exc.detail) from exc


def _check_account_can_join(user: User, org_id: int) -> None:
    """Whether an EXISTING account can join the institution, without looking at who invites. 409 otherwise.

    Administrators cannot (a general admin has no institution; an institution admin cannot change institution), nor can
    a deactivated account or one that never verified its mail (it could not even log in to accept), nor an account that
    is already a member of this institution (its role is changed from Usuarios).
    """
    if user.role == "admin":
        raise InvitationError(409, "Esa cuenta es de un administrador general y no puede unirse a una institución")
    if user.role == "org_admin":
        raise InvitationError(409, "Esa cuenta es administradora de una institución y no puede cambiar de institución")
    if not user.is_active:
        raise InvitationError(409, "La cuenta de ese mail está desactivada")
    if user.email_verified_at is None:
        raise InvitationError(409, "La cuenta de ese mail todavía no verificó su mail: que lo verifique primero")
    if user.organization_id == org_id:
        raise InvitationError(409, "Esa cuenta ya pertenece a esta institución: cambiale el rol desde Usuarios")


def _check_existing_account(actor: User, org: Organization, user: User) -> None:
    """The rules when `actor` invites a mail that has an account. Besides _check_account_can_join: an
    institution admin cannot take someone from ANOTHER institution (only the general admin moves people)."""
    _check_account_can_join(user, org.id)
    if user.organization_id is not None and actor.role != "admin":
        raise InvitationError(
            409, "Esa cuenta ya pertenece a otra institución: pedile al administrador general que la mueva"
        )


def account_info(db: Session, invitations: List[Invitation]) -> Dict[object, Tuple[bool, Optional[str]]]:
    """For each invitation: does its mail have an account NOW, and the name of the institution that account is in
    when it is a different one (the one it would leave). One query for all of them. Worked out when asked (the account
    may have been created or deleted after the invitation), never stored."""
    emails = {row.email for row in invitations}
    if not emails:
        return {}
    found = {
        email: org_name
        for email, org_name in db.query(User.email, Organization.name)
        .outerjoin(Organization, Organization.id == User.organization_id)
        .filter(User.email.in_(emails))
        .all()
    }
    info = {}
    for row in invitations:
        exists = row.email in found
        org_name = found.get(row.email)
        leaves = org_name if exists and org_name is not None and org_name != row.organization.name else None
        info[row.id] = (exists, leaves)
    return info


def create_invitation(
    db: Session,
    actor: User,
    organization_id: int,
    email: str,
    role: str,
    radar_views: Optional[List[str]],
    now: Optional[datetime] = None,
    within_company: bool = False,
    tools: Optional[dict] = None,
) -> Tuple[Invitation, OutgoingMail]:
    """Invite `email` to the institution with `role`. Returns the invitation and the mail to send.

    `tools` are the tools the viewer starts with, as {tool name: bool}; a tool not named (or None) is a copy of the
    institution's when the invitation is accepted.

    Rules (all checked with the institution row locked, so two simultaneous invitations cannot both take the last
    seat): the institution is active (409), no pending invitation of another institution (409; one of the same
    institution is REPLACED, which is what "resend" does), a viewer needs an active admin in the institution (409), a
    seat is free counting the pending invitations (409), and the sending caps are respected (429).

    A mail that already has an account is NOT refused any more: the invitation is made and the mail goes out;
    the answer says the account exists. It is refused only for accounts that cannot join (see _check_existing_account).
    """
    now = _now(now)
    email = normalize_email(email)
    try:
        org = organizations.lock_org(db, organization_id)
    except organizations.OrgRuleError as exc:
        raise InvitationError(exc.status_code, exc.detail) from exc
    if not org.is_active:
        raise InvitationError(409, f"La institución {org.name} está inactiva")
    views = _clean_views(db, role, radar_views)
    if within_company and views is not None:
        # An institution admin may only hand out views its institution has, as when it creates a user.
        try:
            permissions.ensure_within_org(org, set(views))
        except permissions.PermissionRuleError as exc:
            raise InvitationError(exc.status_code, exc.detail) from exc
    tools = {name: bool(on) for name, on in (tools or {}).items() if name in permissions.TOOLS and on is not None}
    if tools and role != "viewer":
        raise InvitationError(422, "Solo un lector lleva la elección de herramientas")
    if within_company and any(
        on and not permissions.stored_tool(org, permissions.TOOLS[name]) for name, on in tools.items()
    ):
        raise InvitationError(403, "Solo podés asignar herramientas que tenga tu institución")

    existing = get_user_by_email(db, email)
    if existing is not None:
        _check_existing_account(actor, org, existing)
    open_ones = db.query(Invitation).filter(Invitation.email == email, *_pending_filters(now)).all()
    if any(row.organization_id != org.id for row in open_ones):
        raise InvitationError(409, "Ese mail ya tiene una invitación pendiente de otra institución")
    if role == "viewer":
        try:
            organizations.ensure_org_has_admin(db, org.id)
        except organizations.OrgRuleError as exc:
            raise InvitationError(exc.status_code, exc.detail) from exc

    replaced = [row.id for row in open_ones]
    used = organizations.seats_used(db, org)
    reserved = organizations.pending_invitations(db, org.id) - len(replaced)
    if used + reserved >= org.seat_limit:
        raise InvitationError(409, f"La institución {org.name} no tiene lugares libres ({used} de {org.seat_limit})")
    _check_may_send(db, email, now)

    for row in open_ones:
        row.cancelled_at = now
    token = generate_token()
    invitation = Invitation(
        email=email,
        organization_id=org.id,
        role=role,
        radar_views=views,
        tools=tools or None,
        token_hash=hash_token(token),
        invited_by=actor.id,
        created_at=now,
        expires_at=now + timedelta(days=settings.invitation_ttl_days),
    )
    db.add(invitation)
    db.flush()
    mail = invitation_mail(db, email, org.name, role, actor.full_name or actor.username, token, invitation.expires_at)
    return invitation, mail


def pending_of(db: Session, organization_id: Optional[int] = None, now: Optional[datetime] = None) -> List[Invitation]:
    """The pending invitations (of one institution, or of all), newest first."""
    query = db.query(Invitation).filter(*_pending_filters(_now(now)))
    if organization_id is not None:
        query = query.filter(Invitation.organization_id == organization_id)
    return query.order_by(Invitation.created_at.desc()).all()


def get_pending(
    db: Session, invitation_id, organization_id: Optional[int] = None, now: Optional[datetime] = None
) -> Invitation:
    """A pending invitation by id (locked), or 404. With `organization_id`, one of another institution is 404 too:
    an institution admin must not learn which ids exist elsewhere."""
    try:
        key = invitation_id if isinstance(invitation_id, uuid.UUID) else uuid.UUID(str(invitation_id))
    except ValueError:  # not a UUID: the same "not found" as an unknown one, without touching the database
        raise InvitationError(404, "Invitación no encontrada")
    row = (
        db.query(Invitation).filter(Invitation.id == key, *_pending_filters(_now(now))).with_for_update().one_or_none()
    )
    if row is None or (organization_id is not None and row.organization_id != organization_id):
        raise InvitationError(404, "Invitación no encontrada")
    return row


def cancel(db: Session, invitation: Invitation, now: Optional[datetime] = None) -> None:
    """Close a pending invitation: its link stops working and its seat is free again."""
    invitation.cancelled_at = _now(now)
    db.flush()


def resend(
    db: Session, actor: User, invitation: Invitation, now: Optional[datetime] = None
) -> Tuple[Invitation, OutgoingMail]:
    """A new link for the same person: the old invitation is replaced by a new one with the same data."""
    return create_invitation(
        db,
        actor,
        invitation.organization_id,
        invitation.email,
        invitation.role,
        invitation.radar_views,
        now,
        tools=invitation.tools,
    )


# --- the person opens the link ------------------------------------------------------------------------------


def find_by_token(db: Session, token: str, lock: bool = False, now: Optional[datetime] = None) -> Invitation:
    """The pending invitation of a link. A malformed, unknown, expired, used or cancelled token all raise the same
    404 and run the same query, so the answer does not tell them apart. `lock` is FOR UPDATE: two simultaneous
    requests with one link wait for each other, so the link cannot be accepted twice."""
    if not isinstance(token, str) or not TOKEN_RE.match(token):
        raise InvitationError(404, INVALID_LINK)
    query = db.query(Invitation).filter(Invitation.token_hash == hash_token(token), *_pending_filters(_now(now)))
    row = (query.with_for_update() if lock else query).one_or_none()
    if row is None:
        raise InvitationError(404, INVALID_LINK)
    return row


def _check_institution(db: Session, invitation: Invitation) -> Organization:
    """Checks of the institution when accepting, under its lock: active, a seat for this person (its own reservation is
    not counted against it) and an admin for a viewer (409)."""
    try:
        org = organizations.reserve_seat(db, invitation.organization_id, excluding_invitation=invitation.id)
        if invitation.role == "viewer":
            organizations.ensure_org_has_admin(db, org.id)
    except organizations.OrgRuleError as exc:
        raise InvitationError(exc.status_code, exc.detail) from exc
    if not org.is_active:
        raise InvitationError(409, f"La institución {org.name} está inactiva")
    return org


def _prepare_accept(db: Session, invitation: Invitation) -> Organization:
    """Checks for accepting by CREATING an account (form or Google): the institution's, and the mail free (409)."""
    org = _check_institution(db, invitation)
    if get_user_by_email(db, invitation.email) is not None:
        raise InvitationError(409, "Ya existe una cuenta con ese mail")
    return org


def _apply_invited_tools(db: Session, invitation: Invitation, user: User, granter: User) -> None:
    """The tools of a viewer's invitation: a copy of the institution's tools, then the ones the inviter chose on top."""
    permissions.copy_company_tools_to(db, user, granter)
    if invitation.role == "viewer" and invitation.tools:
        permissions.set_user_tools(db, user, invitation.tools, granter)


def _finish(db: Session, invitation: Invitation, user: User, now: datetime) -> User:
    """Give the new account the views and tools of the invitation and close it. A viewer without a list starts with a
    copy of the institution's list, and without a tool choice with a copy of the institution's tools; an institution
    admin sees the institution's list and has none of its own."""
    if invitation.role == "viewer":
        granter = db.get(User, invitation.invited_by) if invitation.invited_by else None
        granter = granter or user
        if invitation.radar_views is None:
            permissions.copy_company_views_to(db, user, granter)
        else:
            permissions.replace_user_radar_views(db, user, invitation.radar_views, granter)
        _apply_invited_tools(db, invitation, user, granter)
    invitation.accepted_at = now
    user.last_login_at = now
    db.flush()
    return user


def accept_with_password(
    db: Session,
    token: str,
    username: str,
    password: str,
    full_name: Optional[str],
    now: Optional[datetime] = None,
) -> User:
    """Create the account from the form. The mail comes confirmed (opening the link proves the mailbox is theirs).

    Everything runs in one transaction: if the username is taken (409) or the data is invalid (422) nothing is left
    behind and the link keeps working.
    """
    now = _now(now)
    invitation = find_by_token(db, token, lock=True, now=now)
    org = _prepare_accept(db, invitation)
    try:
        with db.begin_nested():
            user = create_user(
                db,
                username=username,
                password=password,
                role=invitation.role,
                organization_id=org.id,
                full_name=normalize_full_name(full_name),
                email=invitation.email,
                email_verified=True,
            )
            return _finish(db, invitation, user, now)
    except UsernameTakenError as exc:
        raise InvitationError(409, str(exc)) from exc
    except EmailTakenError as exc:
        raise InvitationError(409, "Ya existe una cuenta con ese mail") from exc
    except (AccountError, PasswordPolicyError) as exc:
        raise InvitationError(422, str(exc)) from exc


def accept_with_google(db: Session, token: str, identity: GoogleIdentity, now: Optional[datetime] = None) -> User:
    """Create the account from a Google identity. Google must have verified the mail, and it must be the invited one
    (the link is not a key that can be passed on: only the owner of that mailbox comes in). The account has no usable
    password; it signs in with Google (or asks for a password reset)."""
    now = _now(now)
    invitation = find_by_token(db, token, lock=True, now=now)
    if not identity.email_verified:
        raise GoogleLoginError(
            403, "Google no confirmó tu mail, no podemos usarlo para entrar", "google_email_unverified"
        )
    if normalize_email(identity.email) != invitation.email:
        raise GoogleLoginError(
            403,
            "El mail de tu cuenta de Google no es el de la invitación. Entrá con la cuenta de Google de ese mail",
            "invitation_email_mismatch",
        )
    org = _prepare_accept(db, invitation)
    if db.query(User).filter(User.google_sub == identity.sub).first() is not None:
        raise InvitationError(409, "Esa cuenta de Google ya está enlazada a otro usuario")
    try:
        with db.begin_nested():
            user = create_user(
                db,
                username=_free_username(db, invitation.email),
                password=_unusable_password(),
                role=invitation.role,
                organization_id=org.id,
                full_name=normalize_full_name(identity.name),
                email=invitation.email,
                email_verified=True,
                google_sub=identity.sub,
            )
            return _finish(db, invitation, user, now)
    except EmailTakenError as exc:
        raise InvitationError(409, "Ya existe una cuenta con ese mail") from exc
    except (AccountError, PasswordPolicyError) as exc:
        raise InvitationError(422, str(exc)) from exc


def accept_existing(db: Session, session_user: User, token: str, now: Optional[datetime] = None) -> User:
    """Join the institution with the account that is logged in. The router has already authenticated it.

    It takes BOTH the link and a session of the account of the invited mail (403 otherwise, without showing the mail):
    the link alone cannot enter anybody's account, and knowing a password alone cannot join an institution. Everything
    is checked again at this moment, with the institution locked: the account is still a plain active viewer, it is not
    already in this institution, the institution is active, has a free seat and an admin for a viewer, and, if the
    person is in ANOTHER institution, only a general admin may have invited it (the inviter is read now; if it no
    longer exists the most restrictive rule applies).

    Then the person leaves the old institution (its seat is free again by itself, seats being the active users),
    enters the new one, becomes its admin if the invitation says so, and gets the views of the invitation (a copy of the
    institution's list when none was chosen, replacing the ones it had). All its sessions are closed; the router opens a
    new one, so the person is inside with the new permissions.
    """
    now = _now(now)
    invitation = find_by_token(db, token, lock=True, now=now)
    if session_user.email is None or normalize_email(session_user.email) != invitation.email:
        raise InvitationError(
            403, "Esta invitación es para otra cuenta. Cerrá sesión e ingresá con la cuenta del mail invitado"
        )
    user = session_user
    _check_account_can_join(user, invitation.organization_id)
    inviter = db.get(User, invitation.invited_by) if invitation.invited_by else None
    if user.organization_id is not None and (inviter is None or inviter.role != "admin"):
        raise InvitationError(
            409, "Esa cuenta ya pertenece a otra institución: pedile al administrador general que te mueva"
        )
    org = _check_institution(db, invitation)

    granter = inviter or user
    user.organization = org
    if invitation.role == "org_admin":
        user.role = "org_admin"
    db.flush()  # the institution and the role first: the views below lock and reload the user
    if invitation.role == "viewer" and invitation.radar_views is not None:
        permissions.replace_user_radar_views(db, user, invitation.radar_views, granter)
    else:
        permissions.copy_company_views_to(db, user, granter)
    if invitation.role == "viewer":
        _apply_invited_tools(db, invitation, user, granter)
    invitation.accepted_at = now
    user.last_login_at = now
    revoke_all_sessions(db, user)
    db.flush()
    return user
