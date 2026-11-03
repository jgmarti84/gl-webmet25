# api/app/schemas/profile.py
"""Request and response bodies of the profile endpoints (spec D): the logged-in user's own data."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ProfileRadarView(BaseModel):
    """A radar the user may open in the one-radar view."""

    code: str
    title: str


class ProfileResponse(BaseModel):
    """What the profile page shows. Read only, except for full_name (see ProfileUpdate)."""

    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str
    organization_name: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    # What the user may open now (the same list /permissions/me gives, with the radar titles).
    radar_detail_views: List[ProfileRadarView]


class ProfileUpdate(BaseModel):
    """PATCH body. Only full_name can be changed here: any other field sent is ignored (pydantic drops it)."""

    full_name: Optional[str] = Field(None, max_length=128)

    @field_validator("full_name")
    @classmethod
    def _trim(cls, value: Optional[str]) -> Optional[str]:
        """Spaces at both ends are removed; an empty name means "no name" (null)."""
        if value is None:
            return None
        value = value.strip()
        return value or None
