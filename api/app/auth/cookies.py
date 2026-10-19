# api/app/auth/cookies.py
"""Auth cookies. __Host-/__Secure- prefixes need Secure, so names change in local HTTP."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import Response

from ..config import settings

REFRESH_COOKIE_PATH = f"{settings.api_prefix}/auth"


def access_cookie_name() -> str:
    return "__Host-webmet_access" if settings.cookie_secure else "webmet_access"


def refresh_cookie_name() -> str:
    return "__Secure-webmet_refresh" if settings.cookie_secure else "webmet_refresh"


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    refresh_expires_at: datetime,
    now: Optional[datetime] = None,
) -> None:
    now = now or datetime.now(timezone.utc)
    response.set_cookie(
        access_cookie_name(),
        access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        refresh_cookie_name(),
        refresh_token,
        max_age=max(0, int((refresh_expires_at - now).total_seconds())),
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        access_cookie_name(), path="/", secure=settings.cookie_secure, httponly=True, samesite="strict"
    )
    response.delete_cookie(
        refresh_cookie_name(),
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
