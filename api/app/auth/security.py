# api/app/auth/security.py
"""JWT access tokens and opaque refresh tokens. No database access here."""

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from ..config import settings

ALGORITHM = "HS256"


class InvalidAccessToken(Exception):
    """The access token is missing, malformed, expired or not ours."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    role: str
    token_version: int
    expires_at: Optional[datetime] = None


def create_access_token(user_id: int, role: str, token_version: int, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        return AccessClaims(
            user_id=int(payload["sub"]),
            role=str(payload["role"]),
            token_version=int(payload["tv"]),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
        )
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError) as exc:
        raise InvalidAccessToken(str(exc)) from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


# secrets.token_urlsafe(32) is always 43 URL-safe characters and never contains a dot.
_REFRESH_SECRET_RE = re.compile(r"[A-Za-z0-9_-]{43}")


def build_refresh_token(session_id: uuid.UUID) -> str:
    """Refresh token "<session id>.<secret>": the id finds the login row, the secret proves possession."""
    return f"{session_id}.{secrets.token_urlsafe(32)}"


def parse_refresh_token(token: str) -> Optional[uuid.UUID]:
    """Session id of a well-formed refresh token, or None (malformed or old format) without touching the database."""
    parts = token.split(".")
    if len(parts) != 2 or not _REFRESH_SECRET_RE.fullmatch(parts[1]):
        return None
    try:
        session_id = uuid.UUID(parts[0])
    except ValueError:
        return None
    # Only the canonical form we issue: rejects hex without dashes, upper case, braces.
    return session_id if str(session_id) == parts[0] else None


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
