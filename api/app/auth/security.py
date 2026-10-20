# api/app/auth/security.py
"""JWT access tokens and opaque refresh tokens. No database access here."""

import hashlib
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
        )
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError) as exc:
        raise InvalidAccessToken(str(exc)) from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
