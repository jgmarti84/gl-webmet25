# api/app/schemas/permissions.py
"""Request and response bodies of the permission endpoints (spec C)."""

from typing import Annotated, List

from pydantic import BaseModel, Field, StringConstraints

# A radar code (letters, digits, "_" or "-", like the radars table) or "*" for every radar.
RadarResource = Annotated[str, StringConstraints(min_length=1, max_length=16, pattern=r"^(\*|[A-Za-z0-9_-]+)$")]


class RadarViewsUpdate(BaseModel):
    """PUT body: the whole new list of one-radar detail views ([] removes them all, ["*"] grants all)."""

    radar_detail_view: List[RadarResource] = Field(max_length=500)


class MyPermissionsResponse(BaseModel):
    """What the logged-in user may open, already resolved: real radar codes, never "*"."""

    radar_detail_views: List[str]
