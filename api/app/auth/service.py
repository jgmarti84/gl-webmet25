# api/app/auth/service.py
"""Login, refresh rotation and logout. Functions flush; routers commit."""

import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from radar_db.accounts import find_by_identifier
from radar_db.models import User, UserSession
from radar_db.passwords import DUMMY_HASH, verify_and_update, verify_password

from ..config import settings
from .security import build_refresh_token, hash_refresh_token, parse_refresh_token

GENERIC_LOGIN_ERROR = "Usuario o contraseña incorrectos"
# A refresh token reused this soon after rotation is treated as two tabs racing,
# not as theft (the browser already holds the new cookie).
REFRESH_RACE_WINDOW = timedelta(seconds=10)

# Values of user_sessions.revoke_reason set here ("admin" is set by radar_db.accounts.revoke_all_sessions).
REVOKE_LOGOUT = "logout"
REVOKE_REUSE = "reuse"
REVOKE_INACTIVE_USER = "inactive_user"

# Audit trail of logins, refreshes, logouts and reuse. Never log tokens or their hashes.
logger = logging.getLogger("auth.sessions")


class AuthError(Exception):
    """Authentication failed (always answered with 401)."""


class RefreshRaceError(AuthError):
    """Refresh token reused within the race window; nothing was revoked."""


class EmailNotVerifiedError(Exception):
    """The password was right but the e-mail was never verified (answered with 403, not 401).

    Deliberately not an AuthError: it is only raised after the password checked out, so saying it does not
    reveal anything to someone who does not already know the password.
    """


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.now(timezone.utc)


def authenticate(db: Session, username: str, password: str, now: Optional[datetime] = None) -> User:
    now = _now(now)
    # `username` may be a username or an e-mail (usernames can never contain "@", so there is no ambiguity).
    user = find_by_identifier(db, username)

    if user is None or not user.can_sign_in or (user.locked_until and user.locked_until > now):
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

    # Only after the password is right, so a wrong guess still gets the generic 401 and the unverified state
    # cannot be probed. Nothing is reset or saved here: the person has not logged in.
    if user.email_verified_at is None:
        raise EmailNotVerifiedError("Tenés que verificar tu mail para entrar")

    if new_hash:
        user.password_hash = new_hash
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.flush()
    return user


def _short(session_id: uuid.UUID) -> str:
    """First 8 characters of a login id: enough to follow it in the logs, useless to rebuild a token."""
    return str(session_id)[:8]


def _close(session: UserSession, reason: str, now: datetime) -> None:
    """Mark a login as closed, recording when and why (see the REVOKE_* values)."""
    session.revoked_at = now
    session.revoke_reason = reason


def _hash_matches(token_hash: str, stored: Optional[str]) -> bool:
    """Constant-time comparison of two token hashes; a missing stored hash never matches."""
    return stored is not None and hmac.compare_digest(token_hash, stored)


def create_session(
    db: Session,
    user: User,
    *,
    user_agent: Optional[str] = None,
    ip: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Tuple[UserSession, str]:
    """Open a login: one row that every refresh of this login updates in place."""
    now = _now(now)
    session_id = uuid.uuid4()
    token = build_refresh_token(session_id)
    absolute_expires_at = now + timedelta(days=settings.session_absolute_ttl_days)
    session = UserSession(
        id=session_id,
        user_id=user.id,
        token_hash=hash_refresh_token(token),
        expires_at=min(now + timedelta(hours=settings.session_idle_ttl_hours), absolute_expires_at),
        absolute_expires_at=absolute_expires_at,
        refresh_count=0,
        created_at=now,
        last_used_at=now,
        user_agent=(user_agent or "")[:256] or None,
        ip=ip,
    )
    db.add(session)
    db.flush()
    _purge_old_sessions(db, user.id, now)
    logger.info("login user=%s session=%s ip=%s", user.id, _short(session_id), ip)
    return session, token


def _purge_old_sessions(db: Session, user_id: int, now: datetime) -> int:
    """Delete this user's logins closed or expired more than SESSION_RETENTION_DAYS ago.

    Runs on every login of that user, so the table stays bounded without a scheduled job.
    """
    cutoff = now - timedelta(days=settings.session_retention_days)
    deleted = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            or_(UserSession.revoked_at < cutoff, UserSession.absolute_expires_at < cutoff),
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    return deleted


def _lock_session(db: Session, token: str) -> Optional[UserSession]:
    """The login row of a well-formed token, locked until the transaction ends (one refresh at a time).

    SELECT ... FOR UPDATE: a second refresh of the same login waits here until the first one commits,
    and then sees the already rotated row.
    """
    session_id = parse_refresh_token(token)
    if session_id is None:
        return None
    return db.query(UserSession).filter(UserSession.id == session_id).with_for_update().one_or_none()


def rotate_refresh(
    db: Session,
    token: str,
    *,
    user_agent: Optional[str] = None,
    ip: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Tuple[User, UserSession, str]:
    """Renew a login: rotate its token in place, wait out a refresh race, or close it on reuse."""
    now = _now(now)
    session = _lock_session(db, token)
    if session is None or session.revoked_at is not None:
        raise AuthError("Sesión inválida")
    # Before comparing hashes: an old token of an expired login is not a theft worth acting on.
    if session.expires_at <= now or session.absolute_expires_at <= now:
        raise AuthError("Sesión vencida")

    token_hash = hash_refresh_token(token)
    if _hash_matches(token_hash, session.token_hash):
        user = db.get(User, session.user_id)
        # An unverified account is treated like an inactive one (defense in depth: it should have no login).
        if user is None or not user.can_sign_in or user.email_verified_at is None:
            _close(session, REVOKE_INACTIVE_USER, now)
            db.flush()
            raise AuthError("Sesión inválida")
        new_token = build_refresh_token(session.id)
        session.previous_token_hash = session.token_hash
        session.token_hash = hash_refresh_token(new_token)
        session.rotated_at = now
        session.last_used_at = now
        session.expires_at = min(now + timedelta(hours=settings.session_idle_ttl_hours), session.absolute_expires_at)
        session.refresh_count += 1
        db.flush()
        logger.info("refresh user=%s session=%s ip=%s", user.id, _short(session.id), ip)
        return user, session, new_token

    if (
        _hash_matches(token_hash, session.previous_token_hash)
        and session.rotated_at is not None
        and now - session.rotated_at < REFRESH_RACE_WINDOW
    ):
        # Another tab of the same browser rotated it a moment ago and already holds the new cookie.
        # Never hand out a token here: the previous token only buys a wait.
        raise RefreshRaceError("Refresh en curso")

    # An old (or invented) token of this login: somebody else has a copy. Close the login and kill every
    # access token of the user; their other logins renew silently with their own refresh tokens.
    _close(session, REVOKE_REUSE, now)
    user = db.get(User, session.user_id)
    if user is not None:
        user.token_version += 1
    db.flush()
    logger.warning(
        "reuse user=%s session=%s ip=%s ua=%s", session.user_id, _short(session.id), ip, (user_agent or "")[:256]
    )
    raise AuthError("Sesión inválida")


def revoke_session_by_token(db: Session, token: str, now: Optional[datetime] = None) -> None:
    """Logout. A token that is neither the current nor the previous one changes nothing (no theft logic)."""
    session = _lock_session(db, token)
    if session is None or session.revoked_at is not None:
        return
    token_hash = hash_refresh_token(token)
    if _hash_matches(token_hash, session.token_hash) or _hash_matches(token_hash, session.previous_token_hash):
        _close(session, REVOKE_LOGOUT, _now(now))
        db.flush()
        logger.info("logout user=%s session=%s", session.user_id, _short(session.id))


def load_active_user(db: Session, user_id: int, token_version: int) -> Optional[User]:
    """Decision D11 (see spec): every authenticated request reads the user (and its company: spec C)."""
    user = db.get(User, user_id)
    if user is None or not user.can_sign_in or user.email_verified_at is None or user.token_version != token_version:
        return None
    return user
