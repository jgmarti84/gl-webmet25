# api/app/routers/permissions.py
"""The logged-in user's own permissions (spec C). Read by the map and radar.html when they load."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.models import User

from ..auth.dependencies import get_current_user
from ..auth.permissions import effective_radar_views
from ..schemas.permissions import MyPermissionsResponse

router = APIRouter(prefix="/permissions", tags=["Permissions"])


@router.get("/me", response_model=MyPermissionsResponse)
def my_permissions(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> MyPermissionsResponse:
    """One-radar detail views the user may open (wildcard expanded, view flag applied)."""
    return MyPermissionsResponse(radar_detail_views=effective_radar_views(db, user))
