# api/app/auth/organizations.py
"""Company accounts (spec C §5): seats, creating company users, editing companies. Functions flush; routers commit."""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar_db.accounts import AccountError, EmailTakenError, UsernameTakenError, create_user, revoke_all_sessions
from radar_db.models import Organization, User
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


def lock_org(db: Session, org_id: int) -> Organization:
    """Read the company row with FOR UPDATE: two sign-ups for the last seat then run one after the other."""
    org = db.query(Organization).filter(Organization.id == org_id).with_for_update().one_or_none()
    if org is None:
        raise OrgRuleError(404, "Institución no encontrada")
    return org


def reserve_seat(db: Session, org_id: int) -> Organization:
    """Lock the company and fail with 409 when every seat is taken (create or reactivate, decision C10)."""
    org = lock_org(db, org_id)
    used = seats_used(db, org)
    if used >= org.seat_limit:
        raise OrgRuleError(409, f"La institución {org.name} no tiene lugares libres ({used} de {org.seat_limit})")
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


def move_user(db: Session, actor: User, user: User, target_org_id: Optional[int]) -> None:
    """Put an existing viewer into a company, move it to another, or take it out (None). Only the general admin.

    Joining takes a seat (409 when the company is full or inactive) unless the account is inactive, which only takes
    one when it is reactivated. The account's own views are REPLACED by a copy of the company's list, the same start a
    new member gets (no intersection), and its sessions are closed because what it can see changes. Leaving frees the
    seat and keeps the list it has. Asking for the company it already has does nothing.
    """
    if target_org_id == user.organization_id:
        return
    if actor.role != "admin":
        raise OrgRuleError(403, "Solo el administrador general puede mover cuentas entre instituciones")
    if user.role != "viewer":
        raise OrgRuleError(422, "Solo se pueden mover lectores: los administradores no cambian de institución")

    if target_org_id is None:
        user.organization = None
    else:
        # Locked even for an inactive account, so the company cannot be deactivated or resized under our feet.
        org = reserve_seat(db, target_org_id) if user.is_active else lock_org(db, target_org_id)
        if not org.is_active:
            raise OrgRuleError(409, f"La institución {org.name} está inactiva")
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
    move_user(db, actor, user, org.id)
    user.role = "org_admin"
    db.flush()


def create_org_with_admin(db: Session, actor: User, data: dict, admin, views: Optional[list]) -> Organization:
    """New company plus, optionally, its radar views and its admin, all or nothing.

    `admin` is a NewOrgAdmin / ExistingOrgAdmin (or None) and `views` a list of radar codes or ["*"] (or None). It all
    runs inside one savepoint, so if any step fails (name taken, bad radar, username taken, weak password, a user that
    cannot be chosen...) nothing is left behind, not even the company. The views are set BEFORE the admin is created,
    so the admin starts with the company's list.
    """
    with db.begin_nested():
        org = create_org(db, data)
        if views:
            permissions.replace_org_radar_views(db, org, views, actor)
        if admin is not None and admin.mode == "new":
            fields = admin.model_dump(exclude={"mode"})
            create_member(db, org.id, fields, "org_admin", actor)
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
