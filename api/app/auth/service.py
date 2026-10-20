# api/app/auth/service.py
"""Login, refresh rotation and logout. Functions flush; routers commit."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from radar_db.accounts import get_user_by_username, normalize_username
from radar_db.models import User, UserSession
from radar_db.passwords import DUMMY_HASH, verify_and_update, verify_password

from ..config import settings
from .security import generate_refresh_token, hash_refresh_token

GENERIC_LOGIN_ERROR = "Usuario o contraseña incorrectos"
# A refresh token reused this soon after rotation is treated as two tabs racing,
# not as theft (the browser already holds the new cookie).
REFRESH_RACE_WINDOW = timedelta(seconds=10)


class AuthError(Exception):
    """Authentication failed (always answered with 401)."""


class RefreshRaceError(AuthError):
    """Refresh token reused within the race window; nothing was revoked."""


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.now(timezone.utc)


def authenticate(db: Session, username: str, password: str, now: Optional[datetime] = None) -> User:
    now = _now(now)
    user = get_user_by_username(db, normalize_username(username))

    if user is None or not user.is_active or (user.locked_until and user.locked_until > now):
        verify_password(password, DUMMY_HASH)  # same cost as a real check
        raise AuthError(GENERIC_LOGIN_ERROR)

    ok, new_hash = verify_and_update(password, user.password_hash)
    if not ok:
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_failed_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_count = 0
        db.flush()
        raise AuthError(GENERIC_LOGIN_ERROR)

    if new_hash:
        user.password_hash = new_hash
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.flush()
    return user


def _new_session(
    db: Session,
    user: User,
    *,
    family_id: uuid.UUID,
    absolute_expires_at: datetime,
    now: datetime,
    user_agent: Optional[str],
    ip: Optional[str],
) -> Tuple[UserSession, str]:
    token = generate_refresh_token()
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        family_id=family_id,
        token_hash=hash_refresh_token(token),
        expires_at=min(now + timedelta(hours=settings.session_idle_ttl_hours), absolute_expires_at),
        absolute_expires_at=absolute_expires_at,
        created_at=now,
        last_used_at=now,
        user_agent=(user_agent or "")[:256] or None,
        ip=ip,
    )
    db.add(session)
    db.flush()
    return session, token


def create_session(
    db: Session,
    user: User,
    *,
    user_agent: Optional[str] = None,
    ip: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Tuple[UserSession, str]:
    now = _now(now)
    return _new_session(
        db,
        user,
        family_id=uuid.uuid4(),
        absolute_expires_at=now + timedelta(days=settings.session_absolute_ttl_days),
        now=now,
        user_agent=user_agent,
        ip=ip,
    )


def _find_session(db: Session, token: str) -> Optional[UserSession]:
    return db.query(UserSession).filter(UserSession.token_hash == hash_refresh_token(token)).one_or_none()


def _revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    (
        db.query(UserSession)
        .filter(UserSession.family_id == family_id, UserSession.revoked_at.is_(None))
        .update({UserSession.revoked_at: now}, synchronize_session=False)
    )
    db.flush()


def rotate_refresh(
    db: Session,
    token: str,
    *,
    user_agent: Optional[str] = None,
    ip: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Tuple[User, UserSession, str]:
    now = _now(now)
    current = _find_session(db, token)
    if current is None:
        raise AuthError("Sesión inválida")

    if current.revoked_at is not None:
        if current.replaced_by is not None and now - current.revoked_at < REFRESH_RACE_WINDOW:
            raise RefreshRaceError("Refresh en curso")
        _revoke_family(db, current.family_id, now)
        raise AuthError("Sesión inválida")

    if current.expires_at <= now or current.absolute_expires_at <= now:
        raise AuthError("Sesión vencida")

    user = db.get(User, current.user_id)
    if user is None or not user.is_active:
        current.revoked_at = now
        db.flush()
        raise AuthError("Sesión inválida")

    new_session, new_token = _new_session(
        db,
        user,
        family_id=current.family_id,
        absolute_expires_at=current.absolute_expires_at,
        now=now,
        user_agent=user_agent,
        ip=ip,
    )
    current.revoked_at = now
    current.replaced_by = new_session.id
    current.last_used_at = now
    db.flush()
    return user, new_session, new_token


def revoke_session_by_token(db: Session, token: str, now: Optional[datetime] = None) -> None:
    session = _find_session(db, token)
    if session is not None and session.revoked_at is None:
        session.revoked_at = _now(now)
        db.flush()


def load_active_user(db: Session, user_id: int, token_version: int) -> Optional[User]:
    """Decision D11 (see spec): every authenticated request reads the user."""
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        return None
    return user
