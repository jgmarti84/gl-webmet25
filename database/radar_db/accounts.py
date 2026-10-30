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


class EmailTakenError(AccountError):
    """The e-mail already belongs to another account."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_username(username: str) -> str:
    return username.strip().lower()


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Lower case, no surrounding spaces; empty means "no e-mail"."""
    if email is None:
        return None
    value = email.strip().lower()
    return value or None


def normalize_full_name(full_name: Optional[str]) -> Optional[str]:
    """Clean a free-text name: drop non-printable characters and collapse runs of white space into one space.

    Empty (or only blanks) means "no name" and gives None. Used for the optional name of the sign-up form.
    """
    if full_name is None:
        return None
    printable = "".join(ch for ch in full_name if ch.isprintable() or ch.isspace())
    return " ".join(printable.split()) or None


def validate_username(username: str) -> str:
    normalized = normalize_username(username)
    if not USERNAME_RE.match(normalized):
        raise AccountError(
            "El usuario debe tener entre 3 y 32 caracteres: letras minúsculas, números, punto, guion o guion bajo"
        )
    return normalized


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == normalize_username(username)).one_or_none()


def get_user_by_email(db: Session, email: Optional[str]) -> Optional[User]:
    normalized = normalize_email(email)
    if normalized is None:
        return None
    return db.query(User).filter(User.email == normalized).one_or_none()


def find_by_identifier(db: Session, identifier: str) -> Optional[User]:
    """Look up by e-mail when the text has an "@" (usernames can never have one), else by username."""
    value = identifier.strip()
    if "@" in value:
        return get_user_by_email(db, value)
    return get_user_by_username(db, value)


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
    email_verified: bool = True,
    terms_accepted: bool = False,
    password_hash: Optional[str] = None,
    google_sub: Optional[str] = None,
) -> User:
    """Create an account. `password_hash` lets a caller that already hashed the password reuse it.

    Accounts are verified by default (admin panel and CLI); self-registration passes email_verified=False.
    """
    normalized = validate_username(username)
    if role not in USER_ROLES:
        raise AccountError(f"Rol inválido: {role}")
    validate_password(password, normalized)
    if get_user_by_username(db, normalized) is not None:
        raise UsernameTakenError(f"El usuario '{normalized}' ya existe")
    normalized_email = normalize_email(email)
    if normalized_email is not None and get_user_by_email(db, normalized_email) is not None:
        raise EmailTakenError("Ese mail ya está en uso")

    now = _utcnow()
    user = User(
        username=normalized,
        full_name=full_name,
        email=normalized_email,
        password_hash=password_hash or hash_password(password),
        role=role,
        is_active=is_active,
        token_version=0,
        password_is_bootstrap=password_is_bootstrap,
        failed_login_count=0,
        email_verified_at=now if email_verified else None,
        terms_accepted_at=now if terms_accepted else None,
        google_sub=google_sub,
    )
    db.add(user)
    db.flush()
    return user


def revoke_all_sessions(db: Session, user: User, now: Optional[datetime] = None, reason: str = "admin") -> None:
    """Invalidate every access token (token_version) and refresh token of the user.

    reason goes to user_sessions.revoke_reason: "admin" for the panel, the CLI and deactivation;
    "password_reset" when the user recovers their own password by e-mail.
    """
    now = now or _utcnow()
    user.token_version += 1
    (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .update({UserSession.revoked_at: now, UserSession.revoke_reason: reason}, synchronize_session=False)
    )
    db.flush()


def set_password(
    db: Session, user: User, new_password: str, now: Optional[datetime] = None, reason: str = "admin"
) -> None:
    """Change the password, clear the lockout and close every session of the user (with that reason)."""
    validate_password(new_password, user.username)
    user.password_hash = hash_password(new_password)
    user.password_is_bootstrap = False
    user.failed_login_count = 0
    user.locked_until = None
    revoke_all_sessions(db, user, now, reason=reason)


def count_active_admins(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()


def bootstrap_admin(db: Session, username: str, password: str) -> Optional[User]:
    """Create the first admin only if there are no users at all."""
    if db.query(User).count() > 0:
        return None
    return create_user(db, username=username, password=password, role="admin", password_is_bootstrap=True)
