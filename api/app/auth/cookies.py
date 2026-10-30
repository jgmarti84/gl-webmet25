# api/app/auth/cookies.py
"""Auth cookies. __Host-/__Secure- prefixes need Secure, so names change in local HTTP.

Behind a proxy prefix (spec base-path: the proxy strips "/nacho" and sends X-Forwarded-Prefix: /nacho) two copies of
the site share one hostname, and a browser sends a hostname's cookies to both. So the prefix goes into the cookie
NAMES (the access cookie must keep Path=/ because of __Host-) and into the refresh cookie's PATH (the browser asks
for /nacho/api/v1/auth/refresh). Without a prefix everything is exactly as before.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request, Response

from ..config import settings

# Same rule as nginx's map: one simple segment. Anything else counts as no prefix (nginx already sends only valid
# values or ""; checking again protects the API port, which is reachable on the server itself).
_BASE_PATH_RE = re.compile(r"/[A-Za-z0-9_-]+")

REFRESH_COOKIE_PATH = f"{settings.api_prefix}/auth"


def request_base_path(request: Request) -> str:
    """Prefix the browser sees in front of this site ("" at the root), from X-Forwarded-Prefix."""
    value = request.headers.get("x-forwarded-prefix", "")
    return value if _BASE_PATH_RE.fullmatch(value) else ""


def _segment(base_path: str) -> str:
    """Part added to the cookie names: "/nacho" -> "nacho_", and "" -> ""."""
    return f"{base_path[1:]}_" if base_path else ""


def access_cookie_name(base_path: str = "") -> str:
    name = f"{_segment(base_path)}webmet_access"
    return f"__Host-{name}" if settings.cookie_secure else name


def refresh_cookie_name(base_path: str = "") -> str:
    name = f"{_segment(base_path)}webmet_refresh"
    return f"__Secure-{name}" if settings.cookie_secure else name


def refresh_cookie_path(base_path: str = "") -> str:
    """Path the browser uses for the refresh endpoints: "/api/v1/auth", or "/nacho/api/v1/auth" behind a prefix."""
    return f"{base_path}{REFRESH_COOKIE_PATH}"


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    refresh_expires_at: datetime,
    now: Optional[datetime] = None,
    *,
    base_path: str = "",
) -> None:
    now = now or datetime.now(timezone.utc)
    response.set_cookie(
        access_cookie_name(base_path),
        access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.set_cookie(
        refresh_cookie_name(base_path),
        refresh_token,
        max_age=max(0, int((refresh_expires_at - now).total_seconds())),
        path=refresh_cookie_path(base_path),
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_auth_cookies(response: Response, base_path: str = "") -> None:
    response.delete_cookie(
        access_cookie_name(base_path), path="/", secure=settings.cookie_secure, httponly=True, samesite="strict"
    )
    response.delete_cookie(
        refresh_cookie_name(base_path),
        path=refresh_cookie_path(base_path),
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
