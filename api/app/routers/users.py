# api/app/routers/users.py
"""User management (admin only)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.accounts import revoke_all_sessions
from radar_db.models import User

from ..auth import user_admin
from ..auth.dependencies import check_origin, require_admin
from ..schemas.auth import PasswordReset, UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/admin/users", tags=["Admin users"], dependencies=[Depends(check_origin)])


def _response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        email_verified=user.email_verified_at is not None,
        role=user.role,
        is_active=user.is_active,
        password_is_bootstrap=user.password_is_bootstrap,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _get_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def _rule(exc: user_admin.UserRuleError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db), actor: User = Depends(require_admin)) -> List[UserResponse]:
    return [_response(u) for u in user_admin.list_users(db)]


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require_admin)
) -> UserResponse:
    try:
        user = user_admin.create(db, payload.model_dump())
    except user_admin.UserRuleError as exc:
        raise _rule(exc)
    db.commit()
    db.refresh(user)
    return _response(user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_admin)) -> UserResponse:
    return _response(_get_or_404(db, user_id))


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(require_admin)
) -> UserResponse:
    user = _get_or_404(db, user_id)
    try:
        user_admin.update_user(db, actor, user, payload.model_dump(exclude_unset=True))
    except user_admin.UserRuleError as exc:
        raise _rule(exc)
    db.commit()
    db.refresh(user)
    return _response(user)


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: int, payload: PasswordReset, db: Session = Depends(get_db), actor: User = Depends(require_admin)
) -> Response:
    user = _get_or_404(db, user_id)
    try:
        user_admin.reset_password(db, actor, user, payload.password)
    except user_admin.UserRuleError as exc:
        raise _rule(exc)
    db.commit()
    return Response(status_code=204)


@router.post("/{user_id}/revoke-sessions", status_code=204)
def revoke_sessions(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_admin)) -> Response:
    user = _get_or_404(db, user_id)
    revoke_all_sessions(db, user)
    db.commit()
    return Response(status_code=204)
