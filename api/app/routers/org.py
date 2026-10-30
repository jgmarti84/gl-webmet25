# api/app/routers/org.py
"""The company admin's own company (spec C §7.3). No company id in the URL: always the logged-in user's company,
so nobody can reach another company by changing a number (decision C17)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.accounts import revoke_all_sessions
from radar_db.models import User

from ..auth import organizations as orgs
from ..auth import permissions, user_admin
from ..auth.dependencies import check_origin, require_org_admin
from ..schemas.auth import PasswordReset, UserResponse
from ..schemas.organizations import OrganizationResponse, OrgUserCreate, OrgUserUpdate
from ..schemas.permissions import RadarViewsUpdate
from .organizations import org_response
from .users import _response as user_response

router = APIRouter(prefix="/org", tags=["Company admin"], dependencies=[Depends(check_origin)])


def _rule(exc: Exception) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _member_or_404(db: Session, actor: User, user_id: int) -> User:
    """A user of the actor's company. Any other id (another company or none) is 404, never 403: a company admin
    must not learn which ids exist elsewhere."""
    user = db.get(User, user_id)
    if user is None or user.organization_id != actor.organization_id:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def _editable(actor: User, user: User) -> User:
    """Company admins manage the viewers of their company; other company admins are the general admin's job."""
    if user.role != "viewer":
        raise HTTPException(status_code=403, detail="Solo podés administrar a los lectores de tu empresa")
    return user


@router.get("", response_model=OrganizationResponse)
def my_company(db: Session = Depends(get_db), actor: User = Depends(require_org_admin)) -> OrganizationResponse:
    return org_response(db, actor.organization)


@router.get("/users", response_model=List[UserResponse])
def company_users(db: Session = Depends(get_db), actor: User = Depends(require_org_admin)) -> List[UserResponse]:
    users = db.query(User).filter(User.organization_id == actor.organization_id).order_by(User.username).all()
    return [user_response(u) for u in users]


@router.post("/users", response_model=UserResponse, status_code=201)
def create_company_user(
    payload: OrgUserCreate, db: Session = Depends(get_db), actor: User = Depends(require_org_admin)
) -> UserResponse:
    """New viewer in the actor's company: takes a seat and starts with the company's views."""
    try:
        user = orgs.create_member(db, actor.organization_id, payload.model_dump(), "viewer", actor)
    except orgs.OrgRuleError as exc:
        raise _rule(exc)
    db.commit()
    db.refresh(user)
    return user_response(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_company_user(
    user_id: int, payload: OrgUserUpdate, db: Session = Depends(get_db), actor: User = Depends(require_org_admin)
) -> UserResponse:
    user = _editable(actor, _member_or_404(db, actor, user_id))
    try:
        user_admin.update_user(db, actor, user, payload.model_dump(exclude_unset=True))
    except user_admin.UserRuleError as exc:
        raise _rule(exc)
    db.commit()
    db.refresh(user)
    return user_response(user)


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_company_user_password(
    user_id: int, payload: PasswordReset, db: Session = Depends(get_db), actor: User = Depends(require_org_admin)
) -> Response:
    user = _editable(actor, _member_or_404(db, actor, user_id))
    try:
        user_admin.reset_password(db, actor, user, payload.password)
    except user_admin.UserRuleError as exc:
        raise _rule(exc)
    db.commit()
    return Response(status_code=204)


@router.post("/users/{user_id}/revoke-sessions", status_code=204)
def revoke_company_user_sessions(
    user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_org_admin)
) -> Response:
    user = _editable(actor, _member_or_404(db, actor, user_id))
    revoke_all_sessions(db, user)
    db.commit()
    return Response(status_code=204)


@router.put("/users/{user_id}/permissions", response_model=UserResponse)
def set_company_user_permissions(
    user_id: int, payload: RadarViewsUpdate, db: Session = Depends(get_db), actor: User = Depends(require_org_admin)
) -> UserResponse:
    """Replace a member's views, always within the company's views (decision C4)."""
    user = _editable(actor, _member_or_404(db, actor, user_id))
    try:
        permissions.replace_user_radar_views(db, user, payload.radar_detail_view, actor, within_company=True)
    except permissions.PermissionRuleError as exc:
        raise _rule(exc)
    db.commit()
    db.refresh(user)
    return user_response(user)
