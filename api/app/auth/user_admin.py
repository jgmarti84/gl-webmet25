# api/app/auth/user_admin.py
"""Admin rules on top of radar_db.accounts. Functions flush; routers commit."""

from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session, selectinload

from radar_db.accounts import (
    AccountError,
    EmailTakenError,
    UsernameTakenError,
    count_active_admins,
    create_user,
    get_user_by_email,
    normalize_email,
    revoke_all_sessions,
    set_password,
)
from radar_db.models import User
from radar_db.passwords import PasswordPolicyError

from . import organizations, permissions


class UserRuleError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def list_users(db: Session) -> List[User]:
    # selectinload: one extra query for every user's permissions, instead of one per user in the response.
    return (
        db.query(User)
        .options(selectinload(User.permissions), selectinload(User.organization))
        .order_by(User.username)
        .all()
    )


def create(db: Session, data: dict) -> User:
    try:
        return create_user(db, **data)
    except (UsernameTakenError, EmailTakenError) as exc:
        raise UserRuleError(409, str(exc)) from exc
    except (AccountError, PasswordPolicyError) as exc:
        raise UserRuleError(422, str(exc)) from exc


def update_user(db: Session, actor: User, user: User, changes: dict) -> User:
    new_role = changes.get("role")
    deactivating = changes.get("is_active") is False
    demoting = new_role is not None and new_role != "admin" and user.role == "admin"

    # Company rules (spec C): roles must match the company link, and reactivating takes a seat.
    if new_role == "org_admin" and user.organization_id is None:
        raise UserRuleError(422, "Solo un usuario de una empresa puede ser admin de empresa")
    if new_role == "admin" and user.organization_id is not None:
        raise UserRuleError(422, "Un usuario de una empresa no puede ser administrador general")
    reactivating = changes.get("is_active") is True and not user.is_active
    if reactivating and user.organization_id is not None:
        try:
            organizations.reserve_seat(db, user.organization_id)
        except organizations.OrgRuleError as exc:
            raise UserRuleError(exc.status_code, exc.detail) from exc

    if user.id == actor.id and deactivating:
        raise UserRuleError(403, "No podés desactivar tu propia cuenta")
    if user.id == actor.id and demoting:
        raise UserRuleError(403, "No podés quitarte el rol de administrador")
    if user.role == "admin" and user.is_active and (deactivating or demoting):
        if count_active_admins(db) <= 1:
            raise UserRuleError(409, "Tiene que quedar al menos un administrador activo")

    if "full_name" in changes:
        user.full_name = changes["full_name"]
    if "email" in changes:
        # Same rule as sign-up: stored normalized and unique. null clears it.
        new_email = normalize_email(changes["email"])
        if new_email != user.email:
            holder = get_user_by_email(db, new_email)
            if holder is not None and holder.id != user.id:
                raise UserRuleError(409, "Ese mail ya está en uso")
            user.email = new_email
            if user.email_verified_at is None:
                user.email_verified_at = datetime.now(timezone.utc)  # the admin vouches for it

    must_revoke = False
    if new_role is not None and new_role != user.role:
        demoted_company_admin = user.role == "org_admin" and new_role == "viewer"
        user.role = new_role
        must_revoke = True
        if demoted_company_admin:
            # Its own list was ignored while it was a company admin and may be stale: start again from the
            # company's list (spec §5).
            permissions.copy_company_views_to(db, user, actor)
    if "is_active" in changes and changes["is_active"] is not None:
        if changes["is_active"] != user.is_active:
            user.is_active = changes["is_active"]
            must_revoke = must_revoke or not user.is_active

    if must_revoke:
        revoke_all_sessions(db, user)
    db.flush()
    return user


def reset_password(db: Session, actor: User, user: User, new_password: str) -> None:
    if user.id == actor.id:
        raise UserRuleError(
            403,
            "No podés resetear tu propia contraseña desde el panel. "
            f"Desde el servidor: make reset-password U={user.username}",
        )
    try:
        set_password(db, user, new_password)
    except PasswordPolicyError as exc:
        raise UserRuleError(422, str(exc)) from exc


def verify_email(db: Session, user: User) -> User:
    """The admin vouches for the mail of an account whose owner never opened the verification link.

    Same effect as opening the link: the account can log in from now on. Safe to repeat: a mail that is already
    verified keeps its original date. An account with no mail has nothing to verify.
    """
    if user.email is None:
        raise UserRuleError(409, "La cuenta no tiene un mail para verificar")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
        db.flush()
    return user
