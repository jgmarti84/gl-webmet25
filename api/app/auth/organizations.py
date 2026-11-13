# api/app/auth/organizations.py
"""Company accounts: seats, creating company users, editing companies. Functions flush; routers commit."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar_db.accounts import AccountError, EmailTakenError, UsernameTakenError, create_user, revoke_all_sessions
from radar_db.models import Invitation, Organization, User
from radar_db.passwords import PasswordPolicyError

from . import permissions


class OrgRuleError(Exception):
    """A company rule was broken; the router turns it into this HTTP status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class AccountExistsError(OrgRuleError):
    """The username or mail of a new company user already belongs to an account (409).

    A subclass so the company panel can add "ask the general admin" to the message, while the general admin's own
    panel keeps the plain text."""


def seats_used(db: Session, org: Organization) -> int:
    """Active users of the company, company admins included (decision C7)."""
    return db.query(func.count(User.id)).filter(User.organization_id == org.id, User.is_active.is_(True)).scalar() or 0


def pending_invitations(db: Session, org_id: int, excluding: Optional[Any] = None) -> int:
    """Invitations of the institution that are still open (not accepted, cancelled or expired). Each one reserves a
    seat. `excluding` is an invitation id left out of the count (the one being accepted or replaced)."""
    query = db.query(func.count(Invitation.id)).filter(
        Invitation.organization_id == org_id,
        Invitation.accepted_at.is_(None),
        Invitation.cancelled_at.is_(None),
        Invitation.expires_at > datetime.now(timezone.utc),
    )
    if excluding is not None:
        query = query.filter(Invitation.id != excluding)
    return query.scalar() or 0


def _count_active(db: Session, org_id: int, role: Optional[str] = None, excluding: Optional[int] = None) -> int:
    """Active users of an institution, optionally only one role and/or leaving one user out."""
    query = db.query(func.count(User.id)).filter(User.organization_id == org_id, User.is_active.is_(True))
    if role is not None:
        query = query.filter(User.role == role)
    if excluding is not None:
        query = query.filter(User.id != excluding)
    return query.scalar() or 0


def ensure_org_keeps_admin(db: Session, user: User, stays_as_user: bool) -> None:
    """Rule: an institution with at least one ACTIVE user must have at least one ACTIVE admin (409 otherwise).

    Call it BEFORE `user` (an active institution admin) stops being an admin: when it is deactivated or taken out
    (`stays_as_user=False`) or when it is demoted to viewer but stays in the institution (`stays_as_user=True`).
    An institution left with no active users may have no admin, so the last admin can leave together with the last user.
    """
    org = lock_org(db, user.organization_id)
    others = _count_active(db, org.id, excluding=user.id)
    remaining_users = others + (1 if stays_as_user else 0)
    if remaining_users > 0 and _count_active(db, org.id, role="org_admin", excluding=user.id) == 0:
        raise OrgRuleError(
            409,
            f"La institución {org.name} quedaría con usuarios y sin administrador activo: "
            "primero nombrá administrador a otro de sus usuarios",
        )


def ensure_org_has_admin(db: Session, org_id: int) -> None:
    """A viewer can only join or be reactivated in an institution that has an active admin (409 otherwise)."""
    org = lock_org(db, org_id)
    if _count_active(db, org.id, role="org_admin") == 0:
        raise OrgRuleError(
            409, f"La institución {org.name} no tiene un administrador activo: primero creale o activale uno"
        )


def lock_org(db: Session, org_id: int) -> Organization:
    """Read the company row with FOR UPDATE: two sign-ups for the last seat then run one after the other."""
    org = db.query(Organization).filter(Organization.id == org_id).with_for_update().one_or_none()
    if org is None:
        raise OrgRuleError(404, "Institución no encontrada")
    return org


def reserve_seat(db: Session, org_id: int, excluding_invitation: Optional[Any] = None) -> Organization:
    """Lock the company and fail with 409 when every seat is taken (create or reactivate, decision C10).

    Seats held by pending invitations count as taken (spec E), except `excluding_invitation`: the one the person is
    accepting right now (its own seat).
    """
    org = lock_org(db, org_id)
    used = seats_used(db, org)
    reserved = pending_invitations(db, org.id, excluding_invitation)
    if used + reserved >= org.seat_limit:
        detail = f"La institución {org.name} no tiene lugares libres ({used} de {org.seat_limit}"
        detail += f", más {reserved} invitación(es) pendiente(s))" if reserved else ")"
        raise OrgRuleError(409, detail)
    return org


def create_member(db: Session, org_id: int, data: dict, role: str, actor: User) -> User:
    """Create a user inside the company: takes a seat and starts with the company's views (decision C5).

    `data` has username, password, full_name and email. `role` is "viewer" or "org_admin" (only the general admin
    passes "org_admin"). `actor` is recorded as who granted the copied views.
    """
    org = reserve_seat(db, org_id)
    try:
        user = create_user(db, role=role, organization_id=org.id, **data)
    except (UsernameTakenError, EmailTakenError) as exc:
        raise AccountExistsError(409, str(exc)) from exc
    except (AccountError, PasswordPolicyError) as exc:
        raise OrgRuleError(422, str(exc)) from exc
    permissions.copy_company_views_to(db, user, actor)
    return user


def leave_org(db: Session, actor: User, user: User) -> None:
    """Take a viewer out of its institution. Used by the general admin (move to "none") and by the company admin.

    It frees the seat (seats count the ACTIVE users of the company, so the person simply stops being counted), removes
    the radar views and tools the person had (they were a copy of what the institution gave it: someone who leaves must
    not keep seeing the institution's radars) and closes its sessions, because what it can see changes. The account
    stays active and can still log in, as a viewer with no institution and no views. The caller checks who may do
    this.
    """
    # The views go first: replace_user_radar_views locks and reloads the user, which must not happen after the change.
    permissions.replace_user_radar_views(db, user, [], actor)
    # Its tools were a copy of the institution's, like the views: someone who leaves does not keep them.
    permissions.set_user_tools(db, user, {name: False for name in permissions.TOOLS}, actor)
    user.organization = None
    revoke_all_sessions(db, user)
    db.flush()


def move_user(db: Session, actor: User, user: User, target_org_id: Optional[int], becoming_admin: bool = False) -> None:
    """Put an existing viewer into a company, move it to another, or take it out (None). Only the general admin.

    Joining takes a seat (409 when the company is full or inactive) unless the account is inactive, which only takes
    one when it is reactivated. The account's own views are REPLACED by a copy of the company's list, the same start a
    new member gets (no intersection), and its sessions are closed because what it can see changes. Leaving (see
    leave_org) frees the seat and removes its views. Asking for the company it already has does nothing.
    A viewer only joins a company that has an active admin, unless `becoming_admin` (it is about to be that admin).
    """
    if target_org_id == user.organization_id:
        return
    if actor.role != "admin":
        raise OrgRuleError(403, "Solo el administrador general puede mover cuentas entre instituciones")
    if user.role != "viewer":
        raise OrgRuleError(422, "Solo se pueden mover lectores: los administradores no cambian de institución")

    if target_org_id is None:
        leave_org(db, actor, user)
        return
    # Locked even for an inactive account, so the company cannot be deactivated or resized under our feet.
    org = reserve_seat(db, target_org_id) if user.is_active else lock_org(db, target_org_id)
    if not org.is_active:
        raise OrgRuleError(409, f"La institución {org.name} está inactiva")
    if user.is_active and not becoming_admin:
        ensure_org_has_admin(db, org.id)
    user.organization = org
    db.flush()
    permissions.copy_company_views_to(db, user, actor)
    revoke_all_sessions(db, user)
    db.flush()


def create_org(db: Session, data: dict) -> Organization:
    """New company (name, seat_limit, is_active). A taken name answers 409."""
    org = Organization(**data)
    db.add(org)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise OrgRuleError(409, f"Ya existe una institución llamada {data.get('name')}") from exc
    return org


def make_org_admin(db: Session, actor: User, org: Organization, user: User) -> None:
    """An existing viewer WITHOUT a company becomes the admin of `org` (only for a company that was just created).

    It is moved into the company (takes a seat, its sessions are closed, its own views are replaced by the company's,
    see move_user) and its role becomes org_admin. Users of another company are not offered: taking people out of a
    company is a separate feature. Rules are 422, except a user that does not exist (404).
    """
    if user.role != "viewer":
        raise OrgRuleError(422, "Solo un lector sin institución puede ser administrador de la institución")
    if user.organization_id is not None:
        raise OrgRuleError(422, f"El usuario {user.username} ya pertenece a una institución")
    if not user.is_active:
        raise OrgRuleError(422, f"El usuario {user.username} está desactivado")
    move_user(db, actor, user, org.id, becoming_admin=True)
    user.role = "org_admin"
    db.flush()


def create_org_with_admin(
    db: Session,
    actor: User,
    data: dict,
    admin,
    views: Optional[list],
    tools: Optional[dict] = None,
    mails: Optional[list] = None,
    notes: Optional[dict] = None,
) -> Organization:
    """New company plus, optionally, its radar views and its admin, all or nothing.

    `admin` is a NewOrgAdmin / ExistingOrgAdmin / InviteOrgAdmin (or None) and `views` a list of radar codes or ["*"]
    (or None). With an InviteOrgAdmin the invitation is created here and its mail is appended to `mails`, for the
    router to send after the commit (spec E). It all
    runs inside one savepoint, so if any step fails (name taken, bad radar, username taken, weak password, a user that
    cannot be chosen...) nothing is left behind, not even the company. The views are set BEFORE the admin is created,
    so the admin starts with the company's list.
    """
    with db.begin_nested():
        org = create_org(db, data)
        if views:
            permissions.replace_org_radar_views(db, org, views, actor)
        if tools:
            permissions.set_org_tools(db, org, tools, actor)
        if admin is not None and admin.mode == "new":
            fields = admin.model_dump(exclude={"mode"})
            create_member(db, org.id, fields, "org_admin", actor)
        elif admin is not None and admin.mode == "invite":
            from . import invitations  # here, not at the top: invitations imports this module

            invitation, mail = invitations.create_invitation(db, actor, org.id, admin.email, "org_admin", None)
            if mails is not None:
                mails.append(mail)
            if notes is not None:  # the invited mail may already have an account; the panel says so
                notes["existing_account"] = invitations.account_info(db, [invitation])[invitation.id][0]
        elif admin is not None:
            user = db.get(User, admin.user_id)
            if user is None:
                raise OrgRuleError(404, "Usuario no encontrado")
            make_org_admin(db, actor, org, user)
    return org


def update_org(db: Session, org: Organization, changes: dict) -> Organization:
    """Edit name, seat_limit or is_active. Lowering the limit deactivates nobody (spec §5)."""
    for field in ("name", "seat_limit", "is_active"):
        if field in changes and changes[field] is not None:
            setattr(org, field, changes[field])
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise OrgRuleError(409, f"Ya existe una institución llamada {changes.get('name')}") from exc
    return org


def delete_org(db: Session, actor: User, org: Organization, users: str = "block") -> None:
    """Delete an institution for good. Only the general admin (the router requires it). Functions flush; routers commit.

    What happens to the users of the institution (active or inactive, admins included) is chosen with `users`:
    * "block" (default): an institution with users is refused (409) and nothing changes; one without users is deleted.
    * "unlink": every user is set free, as leave_org does for one (its own views are removed, its sessions are closed).
      An institution admin becomes a viewer first, because an admin always needs an institution. The accounts stay
      active (or inactive, if they were), as viewers with no institution and no views.
    * "delete": every user is deleted with its sessions, mail tokens and own views (one SQL DELETE, so the DATABASE
      applies its foreign keys, as in user_admin.delete_user).
    The "an institution keeps an admin" rule does not apply: the institution goes away with its users, so nobody is left
    without an admin. The institution row is locked first (see lock_org), so nobody joins while it is being deleted.

    The institution itself is one SQL DELETE too: the database deletes its own views and ALL its invitations (pending,
    accepted or cancelled) by cascade, so a link that was sent stops working. Other institutions are never touched.
    """
    org = lock_org(db, org.id)
    members = db.query(User).filter(User.organization_id == org.id).all()
    if members and users == "block":
        count = len(members)
        raise OrgRuleError(
            409,
            f"La institución {org.name} tiene {count} {'usuario' if count == 1 else 'usuarios'}: "
            "desvinculalos o eliminalos primero",
        )
    if users == "unlink":
        for member in members:
            if member.role == "org_admin":
                member.role = "viewer"
                db.flush()  # leave_org reloads the user: the new role must already be in the database
            leave_org(db, actor, member)
    elif users == "delete":
        db.query(User).filter(User.organization_id == org.id).delete(synchronize_session=False)
        for member in members:
            db.expunge(member)  # the rows are gone: the session must not keep objects that point at them
    db.flush()
    db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
    db.flush()
    db.expunge(org)
