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
        raise HTTPException(status_code=403, detail="Solo podés administrar a los lectores de tu institución")
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
    """New viewer in the actor's company: takes a seat and starts with the views in the body, which must fit inside
    the company's list, or with a copy of the company's list when the body has none. Account and
    views are saved together: if the views are refused, no account is left behind."""
    try:
        # One savepoint for both steps: if the views are refused the new account is rolled back with them.
        with db.begin_nested():
            user = orgs.create_member(
                db, actor.organization_id, payload.model_dump(exclude={"radar_detail_view"}), "viewer", actor
            )
            if payload.radar_detail_view is not None:
                permissions.replace_user_radar_views(db, user, payload.radar_detail_view, actor, within_company=True)
    except permissions.PermissionRuleError as exc:
        raise _rule(exc)
    except orgs.AccountExistsError as exc:
        # The person may already have an account elsewhere; only the general admin can move it into a company.
        ask = "Si esa persona ya tiene una cuenta, pedile al administrador general que la sume a tu institución."
        raise HTTPException(status_code=exc.status_code, detail=f"{exc.detail}. {ask}")
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
    changes = payload.model_dump(exclude_unset=True)
    # Activating or deactivating accounts is the general admin's job. A company admin takes someone out of its
    # institution with POST .../unlink instead. Refused loudly (not ignored) so nobody thinks it worked.
    if "is_active" in changes:
        raise HTTPException(status_code=403, detail="Solo el administrador general puede activar o desactivar usuarios")
    try:
        user_admin.update_user(db, actor, user, changes)
    except user_admin.UserRuleError as exc:
        raise _rule(exc)
    db.commit()
    db.refresh(user)
    return user_response(user)


@router.post("/users/{user_id}/unlink", response_model=UserResponse)
def unlink_company_user(
    user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_org_admin)
) -> UserResponse:
    """Take a viewer out of the actor's institution: it stops taking a seat, loses the views the institution gave it
    and its sessions are closed. The account stays active (the general admin deactivates). Only viewers of the own
    institution; once unlinked the user is out of reach, like any user of another institution (404)."""
    user = _editable(actor, _member_or_404(db, actor, user_id))
    orgs.leave_org(db, actor, user)
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
