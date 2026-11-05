# api/app/routers/organizations.py
"""Company accounts, managed by the general admin (spec C §7.2)."""

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.models import Organization, User

from ..auth import organizations as orgs
from ..auth import permissions
from ..auth.invitations import InvitationError
from ..auth.dependencies import check_origin, require_admin
from ..mail.service import Mailer, get_mailer
from ..schemas.organizations import OrganizationCreate, OrganizationResponse, OrganizationUpdate
from ..schemas.permissions import RadarViewsUpdate
from .registration import _require_mail, _send_later

router = APIRouter(
    prefix="/admin/organizations",
    tags=["Admin organizations"],
    dependencies=[Depends(require_admin), Depends(check_origin)],
)


def org_response(db: Session, org: Organization) -> OrganizationResponse:
    """Response body of a company: its fields, the seats in use and its saved list of views."""
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        seat_limit=org.seat_limit,
        seats_used=orgs.seats_used(db, org),
        pending_invitations=orgs.pending_invitations(db, org.id),
        is_active=org.is_active,
        radar_detail_views=permissions.stored_org_radar_views(org),
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


def _get_or_404(db: Session, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Institución no encontrada")
    return org


def _rule(exc: Exception) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("", response_model=List[OrganizationResponse])
def list_organizations(db: Session = Depends(get_db)) -> List[OrganizationResponse]:
    return [org_response(db, org) for org in db.query(Organization).order_by(Organization.name).all()]


@router.post("", response_model=OrganizationResponse, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    mailer: Mailer = Depends(get_mailer),
) -> OrganizationResponse:
    """Create a company, optionally with its radar views and its admin (a new user, or an existing viewer without a
    company), all in one transaction: if any part is refused, nothing is created."""
    data = payload.model_dump(exclude={"admin", "radar_detail_view"})
    inviting = payload.admin is not None and payload.admin.mode == "invite"
    if inviting:
        _require_mail()
    mails: list = []  # the invitation mail, if any: sent after the commit
    try:
        org = orgs.create_org_with_admin(db, actor, data, payload.admin, payload.radar_detail_view, mails)
    except (orgs.OrgRuleError, permissions.PermissionRuleError, InvitationError) as exc:
        raise _rule(exc)
    db.commit()
    _send_later(background, mailer, mails)
    db.refresh(org)
    return org_response(db, org)


@router.get("/{org_id}", response_model=OrganizationResponse)
def get_organization(org_id: int, db: Session = Depends(get_db)) -> OrganizationResponse:
    return org_response(db, _get_or_404(db, org_id))


@router.patch("/{org_id}", response_model=OrganizationResponse)
def update_organization(
    org_id: int, payload: OrganizationUpdate, db: Session = Depends(get_db)
) -> OrganizationResponse:
    org = _get_or_404(db, org_id)
    try:
        orgs.update_org(db, org, payload.model_dump(exclude_unset=True))
    except orgs.OrgRuleError as exc:
        raise _rule(exc)
    db.commit()
    db.refresh(org)
    return org_response(db, org)


@router.put("/{org_id}/permissions", response_model=OrganizationResponse)
def set_organization_permissions(
    org_id: int, payload: RadarViewsUpdate, db: Session = Depends(get_db), actor: User = Depends(require_admin)
) -> OrganizationResponse:
    """Replace the company's whole list of views. Members lose at once what the company loses (decision C6)."""
    org = _get_or_404(db, org_id)
    try:
        permissions.replace_org_radar_views(db, org, payload.radar_detail_view, actor)
    except permissions.PermissionRuleError as exc:
        raise _rule(exc)
    db.commit()
    db.refresh(org)
    return org_response(db, org)
