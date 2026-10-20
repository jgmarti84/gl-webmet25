# api/app/auth/user_admin.py
"""Admin rules on top of radar_db.accounts. Functions flush; routers commit."""
from typing import List

from sqlalchemy.orm import Session

from radar_db.accounts import (
    AccountError,
    UsernameTakenError,
    count_active_admins,
    create_user,
    revoke_all_sessions,
    set_password,
)
from radar_db.models import User
from radar_db.passwords import PasswordPolicyError


class UserRuleError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def list_users(db: Session) -> List[User]:
    return db.query(User).order_by(User.username).all()


def create(db: Session, data: dict) -> User:
    try:
        return create_user(db, **data)
    except UsernameTakenError as exc:
        raise UserRuleError(409, str(exc)) from exc
    except (AccountError, PasswordPolicyError) as exc:
        raise UserRuleError(422, str(exc)) from exc


def update_user(db: Session, actor: User, user: User, changes: dict) -> User:
    new_role = changes.get("role")
    deactivating = changes.get("is_active") is False
    demoting = new_role is not None and new_role != "admin" and user.role == "admin"

    if user.id == actor.id and deactivating:
        raise UserRuleError(403, "No podés desactivar tu propia cuenta")
    if user.id == actor.id and demoting:
        raise UserRuleError(403, "No podés quitarte el rol de administrador")
    if user.role == "admin" and user.is_active and (deactivating or demoting):
        if count_active_admins(db) <= 1:
            raise UserRuleError(409, "Tiene que quedar al menos un administrador activo")

    for field in ("full_name", "email"):
        if field in changes:
            setattr(user, field, changes[field])

    must_revoke = False
    if new_role is not None and new_role != user.role:
        user.role = new_role
        must_revoke = True
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
