# api/app/routers/users.py
"""User management (admin only)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.accounts import revoke_all_sessions
from radar_db.models import User

from ..auth import organizations, permissions, user_admin
from ..auth.dependencies import check_origin, require_admin
from ..schemas.auth import PasswordReset, UserCreate, UserResponse, UserUpdate
from ..schemas.permissions import RadarViewsUpdate

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
        radar_detail_views=permissions.stored_radar_views(user),
        organization_id=user.organization_id,
        organization_name=user.organization.name if user.organization else None,
    )


def _get_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def _rule(exc: Exception) -> HTTPException:
    """Both UserRuleError and OrgRuleError carry a status_code and a detail."""
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db), actor: User = Depends(require_admin)) -> List[UserResponse]:
    return [_response(u) for u in user_admin.list_users(db)]


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require_admin)
) -> UserResponse:
    """Create an account. With organization_id it goes into that company: takes a seat, copies its views."""
    data = payload.model_dump()
    organization_id = data.pop("organization_id")
    role = data.pop("role")
    try:
        if organization_id is not None:
            if role == "admin":
                raise user_admin.UserRuleError(422, "Un usuario de una empresa no puede ser administrador general")
            user = organizations.create_member(db, organization_id, data, role, actor)
        elif role == "org_admin":
            raise user_admin.UserRuleError(422, "Solo un usuario de una empresa puede ser admin de empresa")
        else:
            user = user_admin.create(db, {**data, "role": role})
    except (user_admin.UserRuleError, organizations.OrgRuleError) as exc:
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


@router.post("/{user_id}/verify-email", response_model=UserResponse)
def verify_email(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_admin)) -> UserResponse:
    """Mark the mail of an account as verified without the person opening the link (admin only)."""
    user = _get_or_404(db, user_id)
    try:
        user_admin.verify_email(db, user)
    except user_admin.UserRuleError as exc:
        raise _rule(exc)
    db.commit()
    db.refresh(user)
    return _response(user)


@router.put("/{user_id}/permissions", response_model=UserResponse)
def set_user_permissions(
    user_id: int, payload: RadarViewsUpdate, db: Session = Depends(get_db), actor: User = Depends(require_admin)
) -> UserResponse:
    """Replace the user's whole list of one-radar detail views (all or nothing, in one transaction)."""
    user = _get_or_404(db, user_id)
    try:
        permissions.replace_user_radar_views(db, user, payload.radar_detail_view, actor)
    except permissions.PermissionRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    db.commit()
    db.refresh(user)
    return _response(user)
