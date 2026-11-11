# api/app/routers/profile.py
"""The logged-in user's own profile (spec D). No id in the URL: it is always the user of the session, so nobody can
read or change another person's data by changing a number. Every role uses the same two endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.models import Radar, User

from ..auth import user_admin
from ..auth.cookies import clear_auth_cookies, request_base_path
from ..auth.dependencies import check_origin, get_current_user
from ..auth.permissions import effective_radar_views
from ..schemas.profile import ProfileRadarView, ProfileResponse, ProfileUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["Profile"], dependencies=[Depends(check_origin)])


def _profile(db: Session, user: User) -> ProfileResponse:
    """The user's data plus the radars they may open (code and title), already resolved by the permission service."""
    codes = effective_radar_views(db, user)
    titles = dict(db.query(Radar.code, Radar.title).filter(Radar.code.in_(codes)).all()) if codes else {}
    return ProfileResponse(
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        organization_name=user.organization.name if user.organization else None,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        radar_detail_views=[ProfileRadarView(code=code, title=titles.get(code, code)) for code in codes],
    )


@router.get("", response_model=ProfileResponse)
def my_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ProfileResponse:
    """The profile of the logged-in user."""
    return _profile(db, user)


@router.patch("", response_model=ProfileResponse)
def update_my_profile(
    payload: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ProfileResponse:
    """Change the user's own name. Anything else in the body is ignored: username and mail are read only here."""
    changes = payload.model_dump(exclude_unset=True)
    if "full_name" in changes:
        user.full_name = changes["full_name"]
    db.commit()
    db.refresh(user)
    return _profile(db, user)


@router.delete("", status_code=204)
def delete_my_account(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    """Delete the account of the logged-in user for good, whatever the role.

    Like the rest of this router it takes no id (not in the URL, the query or the body): it always acts on the user
    of the session, so nobody can point it at another account. The rules are in user_admin.delete_user (an institution's
    only admin must name another first, a general admin cannot delete itself). The session cookies are cleared so the
    browser does not keep sending a dead session.
    """
    user_id = user.id  # read before the delete: the object is detached from the session afterwards
    try:
        user_admin.delete_user(db, user, user)
    except user_admin.UserRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    db.commit()
    logger.info("user deleted id=%s by=%s", user_id, user_id)
    response = Response(status_code=204)
    clear_auth_cookies(response, request_base_path(request))
    return response
