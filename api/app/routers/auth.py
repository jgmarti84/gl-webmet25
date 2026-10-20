# api/app/routers/auth.py
"""Login, refresh, logout and current user."""
from typing import Optional, Tuple, Union

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.models import User

from ..auth import service
from ..auth.cookies import clear_auth_cookies, refresh_cookie_name, set_auth_cookies
from ..auth.dependencies import check_origin, get_current_user
from ..auth.security import create_access_token
from ..schemas.auth import LoginRequest, MeResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


def _me(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        password_is_bootstrap=user.password_is_bootstrap,
    )


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
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> MeResponse:
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
    return _me(user)


@router.post("/refresh", response_model=MeResponse, dependencies=[Depends(check_origin)])
def refresh(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> Union[MeResponse, JSONResponse]:
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
        db.commit()  # persist a family revocation, if any
        return _unauthorized(str(exc))

    db.commit()
    access_token = create_access_token(user.id, user.role, user.token_version)
    set_auth_cookies(response, access_token, new_token, session.expires_at)
    return _me(user)


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
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return _me(user)
