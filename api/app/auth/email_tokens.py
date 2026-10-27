# api/app/auth/email_tokens.py
"""Single-use e-mail tokens (verify the address, reset the password) and the sending caps (per account and global).

Functions flush; routers commit.
"""

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from radar_db.models import EmailToken, User

from ..config import settings

logger = logging.getLogger(__name__)

# Windows ("hour"/"day", key) whose reached global cap was already logged by this worker (see _warn_once).
_cap_warned: Set[Tuple[str, str]] = set()

PURPOSE_VERIFY = "verify_email"
PURPOSE_RESET = "reset_password"
PURPOSE_NOTICE = "account_exists"

# secrets.token_urlsafe(32) is always 43 URL-safe characters; anything else is not worth a query.
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class InvalidEmailToken(Exception):
    """The token is malformed, unknown, expired or already used."""


def _now(now: Optional[datetime]) -> datetime:
    """The `now` argument exists so tests can move the clock; production passes nothing."""
    return now or datetime.now(timezone.utc)


def generate_token() -> str:
    """A random, unguessable token (256 bits). This is the value that travels in the mail link."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of the token: the only form stored in the database, so a leaked table gives no usable links."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _sent_since(db: Session, since: datetime) -> int:
    """How many mails the whole site sent after `since` (one email_tokens row per mail, of every account)."""
    return db.query(func.count(EmailToken.id)).filter(EmailToken.created_at > since).scalar()


def _warn_once(window: str, key: str, message: str) -> None:
    """Log a reached global cap once per window (per worker), not once per refused mail: under abuse there would
    be thousands of refusals, and a single line is enough to notice it."""
    if (window, key) not in _cap_warned:
        _cap_warned.add((window, key))
        logger.warning(message)


def _global_cap_reached(db: Session, now: datetime, recovery: bool) -> bool:
    """Global caps (all accounts together): MAIL_MAX_GLOBAL_PER_DAY for every mail, MAIL_MAX_GLOBAL_PER_HOUR for
    every mail but password recovery, so real users can still get back in while the sign-up is being abused."""
    if _sent_since(db, now - timedelta(days=1)) >= settings.mail_max_global_per_day:
        _warn_once(
            "day",
            now.strftime("%Y-%m-%d"),
            "MAIL_MAX_GLOBAL_PER_DAY reached: no mail goes out until the 24 h window moves on (abuse of the sign-up, "
            "or the cap is too low for the real traffic)",
        )
        return True
    if not recovery and _sent_since(db, now - timedelta(hours=1)) >= settings.mail_max_global_per_hour:
        _warn_once(
            "hour",
            now.strftime("%Y-%m-%d %H"),
            "MAIL_MAX_GLOBAL_PER_HOUR reached: only password recovery mails go out this hour (abuse of the sign-up, "
            "or the cap is too low for the real traffic)",
        )
        return True
    return False


def may_send_mail(db: Session, user: User, now: Optional[datetime] = None, recovery: bool = False) -> bool:
    """Whether a mail may go out to this account now: per-account caps first, then the global ones.

    Per account: at most MAIL_MAX_PER_HOUR in the last hour and MAIL_MIN_INTERVAL_SECONDS apart. Every row of
    email_tokens counts, whatever its purpose (verify, reset or account_exists notice), so mixing request types
    does not get around the cap. `recovery=True` (a password reset link) is only exempt from the global hourly cap.
    The caller must not send (and must not log a new row) when this returns False, and must answer exactly as if
    it had sent.
    """
    now = _now(now)
    recent = [
        row[0]
        for row in db.query(EmailToken.created_at)
        .filter(EmailToken.user_id == user.id, EmailToken.created_at > now - timedelta(hours=1))
        .all()
    ]
    if len(recent) >= settings.mail_max_per_hour:
        return False
    if recent and max(recent) > now - timedelta(seconds=settings.mail_min_interval_seconds):
        return False
    return not _global_cap_reached(db, now, recovery)


def cancel_open_tokens(db: Session, user: User, purpose: str, now: Optional[datetime] = None) -> None:
    """Mark the user's unused tokens of this purpose as used, so an older link stops working."""
    now = _now(now)
    (
        db.query(EmailToken)
        .filter(EmailToken.user_id == user.id, EmailToken.purpose == purpose, EmailToken.used_at.is_(None))
        .update({EmailToken.used_at: now}, synchronize_session=False)
    )


def issue_token(db: Session, user: User, purpose: str, ttl: timedelta, now: Optional[datetime] = None) -> str:
    """New token; the previous open ones of the same purpose stop working."""
    now = _now(now)
    cancel_open_tokens(db, user, purpose, now)
    token = generate_token()
    db.add(
        EmailToken(user_id=user.id, purpose=purpose, token_hash=hash_token(token), created_at=now, expires_at=now + ttl)
    )
    db.flush()
    return token


def record_notice(db: Session, user: User, now: Optional[datetime] = None) -> None:
    """Log that an "you already have an account" mail went to this account (it counts for the caps).

    The row is born expired and used, with a random hash: nobody can ever redeem it. See EmailToken.
    """
    now = _now(now)
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=PURPOSE_NOTICE,
            token_hash=hash_token(generate_token()),
            created_at=now,
            expires_at=now,
            used_at=now,
        )
    )
    db.flush()


def find_valid_token(db: Session, token: str, purpose: str, now: Optional[datetime] = None) -> EmailToken:
    """Locked row of a usable token. Does not consume it: the caller decides (and marks `used_at`).

    A malformed, unknown, expired, used or wrong-purpose token all raise the same InvalidEmailToken, and the
    lookup is the same query, so the answer does not tell them apart. FOR UPDATE makes two simultaneous
    requests with the same link wait for each other, so the link cannot be redeemed twice.
    """
    now = _now(now)
    if not isinstance(token, str) or not TOKEN_RE.match(token):
        raise InvalidEmailToken()
    row = (
        db.query(EmailToken)
        .filter(EmailToken.token_hash == hash_token(token), EmailToken.purpose == purpose)
        .with_for_update()
        .one_or_none()
    )
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise InvalidEmailToken()
    return row


def consume_token(db: Session, token: str, purpose: str, now: Optional[datetime] = None) -> User:
    """Mark a usable token as used and return its user."""
    now = _now(now)
    row = find_valid_token(db, token, purpose, now)
    row.used_at = now
    db.flush()
    return row.user
