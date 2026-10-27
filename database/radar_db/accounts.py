# database/radar_db/accounts.py
"""Account operations shared by the API and the server CLI.

Functions only flush; the caller decides when to commit.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .models import USER_ROLES, User, UserSession
from .passwords import hash_password, validate_password

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


class AccountError(ValueError):
    """Invalid account data (username, role)."""


class UsernameTakenError(AccountError):
    """The username already exists."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_username(username: str) -> str:
    normalized = normalize_username(username)
    if not USERNAME_RE.match(normalized):
        raise AccountError(
            "El usuario debe tener entre 3 y 32 caracteres: letras minúsculas, números, punto, guion o guion bajo"
        )
    return normalized


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == normalize_username(username)).one_or_none()


def create_user(
    db: Session,
    *,
    username: str,
    password: str,
    role: str,
    full_name: Optional[str] = None,
    email: Optional[str] = None,
    is_active: bool = True,
    password_is_bootstrap: bool = False,
) -> User:
    normalized = validate_username(username)
    if role not in USER_ROLES:
        raise AccountError(f"Rol inválido: {role}")
    validate_password(password, normalized)
    if get_user_by_username(db, normalized) is not None:
        raise UsernameTakenError(f"El usuario '{normalized}' ya existe")

    user = User(
        username=normalized,
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
        token_version=0,
        password_is_bootstrap=password_is_bootstrap,
        failed_login_count=0,
    )
    db.add(user)
    db.flush()
    return user


def revoke_all_sessions(db: Session, user: User, now: Optional[datetime] = None) -> None:
    """Invalidate every access token (token_version) and refresh token of the user."""
    now = now or _utcnow()
    user.token_version += 1
    (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .update({UserSession.revoked_at: now, UserSession.revoke_reason: "admin"}, synchronize_session=False)
    )
    db.flush()


def set_password(db: Session, user: User, new_password: str, now: Optional[datetime] = None) -> None:
    validate_password(new_password, user.username)
    user.password_hash = hash_password(new_password)
    user.password_is_bootstrap = False
    user.failed_login_count = 0
    user.locked_until = None
    revoke_all_sessions(db, user, now)


def count_active_admins(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()


def bootstrap_admin(db: Session, username: str, password: str) -> Optional[User]:
    """Create the first admin only if there are no users at all."""
    if db.query(User).count() > 0:
        return None
    return create_user(db, username=username, password=password, role="admin", password_is_bootstrap=True)
