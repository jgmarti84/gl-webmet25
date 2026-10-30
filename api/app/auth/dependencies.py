# api/app/auth/dependencies.py
"""FastAPI dependencies. Routers only import from here."""

from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.models import User

from ..config import settings
from .cookies import access_cookie_name, request_base_path
from .security import AccessClaims, InvalidAccessToken, decode_access_token
from .service import load_active_user

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def check_origin(request: Request) -> None:
    """CSRF defense in depth: reject state-changing requests from foreign origins."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins_list:
        raise HTTPException(status_code=403, detail="Origen no permitido")


def _user_from_request(request: Request, db: Session) -> Optional[User]:
    # The cookie name depends on the base path the request came through (spec base-path).
    token = request.cookies.get(access_cookie_name(request_base_path(request)))
    if not token:
        return None
    try:
        claims = decode_access_token(token)
    except InvalidAccessToken:
        return None
    return load_active_user(db, claims.user_id, claims.token_version)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _user_from_request(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    return _user_from_request(request, db)


# async on purpose, though it awaits nothing: FastAPI runs a plain "def" dependency in its thread pool
# (40 threads per worker, shared with every sync endpoint). Checking a signature takes microseconds,
# so running it on the event loop is cheaper than waiting for a free thread during a burst of tiles.
async def require_valid_token(request: Request) -> AccessClaims:
    """Session check WITHOUT the database: trusts the signed access token alone.

    Only for public, cheap resources (the basemap tile proxies): it uses no database connection, but a
    deactivated user or a stolen token keeps passing until the access token expires (30 min at most).
    Everything else must use get_current_user, which reads the user on every request (decision D11).
    """
    token = request.cookies.get(access_cookie_name(request_base_path(request)))
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        return decode_access_token(token)
    except InvalidAccessToken:
        raise HTTPException(status_code=401, detail="No autenticado") from None


def require_role(role: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(status_code=403, detail="No tenés permisos para esta acción")
        return user

    return dependency


require_admin = require_role("admin")

# Any logged-in user (admin or viewer). Used for every data router (spec A).
require_user = get_current_user
