# api/app/auth/dependencies.py
"""FastAPI dependencies. Routers only import from here."""

from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.models import User

from ..config import settings
from .cookies import access_cookie_name
from .security import InvalidAccessToken, decode_access_token
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
    token = request.cookies.get(access_cookie_name())
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


def require_role(role: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(status_code=403, detail="No tenés permisos para esta acción")
        return user

    return dependency


require_admin = require_role("admin")
