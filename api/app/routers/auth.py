# api/app/routers/auth.py
"""Login, refresh, logout and current user."""

from datetime import datetime, timezone
from typing import Literal, Optional, Tuple, Union

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.models import User

from ..auth import service
from ..auth.cookies import access_cookie_name, clear_auth_cookies, refresh_cookie_name, set_auth_cookies
from ..auth.dependencies import check_origin, get_current_user
from ..auth.security import create_access_token, decode_access_token
from ..config import settings
from ..schemas.auth import LoginRequest, MeResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


def _me(user: User, access_expires_in: int) -> MeResponse:
    return MeResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        password_is_bootstrap=user.password_is_bootstrap,
        access_expires_in=access_expires_in,
    )


def _full_access_lifetime() -> int:
    return settings.access_token_ttl_minutes * 60


def _client_info(request: Request) -> Tuple[Optional[str], Optional[str]]:
    ip = request.client.host if request.client else None
    return request.headers.get("user-agent"), ip


def _unauthorized(detail: str, code: Optional[str] = None) -> JSONResponse:
    content = {"detail": detail}
    if code:
        content["code"] = code
    response = JSONResponse(status_code=401, content=content)
    clear_auth_cookies(response)
    return response


@router.post("/login", response_model=MeResponse, dependencies=[Depends(check_origin)])
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> MeResponse:
    try:
        user = service.authenticate(db, payload.username, payload.password)
    except service.AuthError:
        db.commit()  # keep the failed-attempt counter
        raise HTTPException(status_code=401, detail=service.GENERIC_LOGIN_ERROR)

    user_agent, ip = _client_info(request)
    session, refresh_token = service.create_session(db, user, user_agent=user_agent, ip=ip)
    db.commit()
    access_token = create_access_token(user.id, user.role, user.token_version)
    set_auth_cookies(response, access_token, refresh_token, session.expires_at)
    return _me(user, _full_access_lifetime())


@router.post("/refresh", response_model=MeResponse, dependencies=[Depends(check_origin)])
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> Union[MeResponse, JSONResponse]:
    token = request.cookies.get(refresh_cookie_name())
    if not token:
        return _unauthorized("No autenticado")

    user_agent, ip = _client_info(request)
    try:
        user, session, new_token = service.rotate_refresh(db, token, user_agent=user_agent, ip=ip)
    except service.RefreshRaceError:
        # Another tab already rotated it; keep the cookies the browser now holds.
        return JSONResponse(status_code=401, content={"detail": "Refresh en curso", "code": "refresh_race"})
    except service.AuthError as exc:
        db.commit()  # persist a login closed on reuse (and the bumped token_version), if any
        return _unauthorized(str(exc))

    db.commit()
    access_token = create_access_token(user.id, user.role, user.token_version)
    set_auth_cookies(response, access_token, new_token, session.expires_at)
    return _me(user, _full_access_lifetime())


@router.post("/logout", status_code=204, dependencies=[Depends(check_origin)])
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(refresh_cookie_name())
    if token:
        service.revoke_session_by_token(db, token)
        db.commit()
    response = Response(status_code=204)
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=MeResponse)
def me(request: Request, user: User = Depends(get_current_user)) -> MeResponse:
    # get_current_user already validated this cookie, so decoding cannot fail here.
    claims = decode_access_token(request.cookies[access_cookie_name()])
    remaining = int((claims.expires_at - datetime.now(timezone.utc)).total_seconds())
    return _me(user, max(0, remaining))


@router.get("/check", status_code=204)
def check(role: Optional[Literal["admin"]] = None, user: User = Depends(get_current_user)) -> Response:
    """Session probe for nginx auth_request: 204 ok, 401 no session, 403 wrong role. Never has a body."""
    if role is not None and user.role != role:
        raise HTTPException(status_code=403, detail="No tenés permisos para esta acción")
    return Response(status_code=204)
