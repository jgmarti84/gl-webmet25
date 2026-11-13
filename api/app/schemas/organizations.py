# api/app/schemas/organizations.py
"""Bodies of the company endpoints (spec C): /admin/organizations and /org."""

from datetime import datetime
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, EmailStr, Field, field_validator

from .permissions import RadarResource, ToolsState, ToolsUpdate


class NewOrgAdmin(BaseModel):
    """A brand new company admin, created together with the company."""

    mode: Literal["new"]
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)
    full_name: Optional[str] = Field(None, max_length=128)
    email: Optional[EmailStr] = None

    @field_validator("username")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().lower()


class ExistingOrgAdmin(BaseModel):
    """An existing viewer without a company who becomes the admin of the new company."""

    mode: Literal["existing"]
    user_id: int


class InviteOrgAdmin(BaseModel):
    """The company admin is invited by mail (spec E): the person creates its own account from the link."""

    mode: Literal["invite"]
    email: EmailStr


# The "mode" field tells which of the three it is (anything else, or no mode, is a 422).
OrgAdminChoice = Annotated[Union[NewOrgAdmin, ExistingOrgAdmin, InviteOrgAdmin], Field(discriminator="mode")]


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    seat_limit: int = Field(..., gt=0, le=10000)
    is_active: bool = True
    # Optional, created in the same transaction as the company: its admin, its radar views (radar codes, or ["*"],
    # the same shape as PUT /organizations/{id}/permissions) and its tools, which are set before the admin is created
    # so the admin starts with them.
    admin: Optional[OrgAdminChoice] = None
    radar_detail_view: Optional[List[RadarResource]] = Field(None, max_length=500)
    tools: Optional[ToolsUpdate] = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    seat_limit: Optional[int] = Field(None, gt=0, le=10000)
    is_active: Optional[bool] = None


class OrganizationResponse(BaseModel):
    id: int
    name: str
    seat_limit: int
    seats_used: int
    # Open invitations (spec E): each one reserves a seat until it is accepted, cancelled or expires.
    pending_invitations: int = 0
    # Only in the answer to "create an institution inviting its admin": that mail already has an account.
    invited_admin_has_account: bool = False
    is_active: bool
    # The company's list as saved: radar codes, or ["*"].
    radar_detail_views: List[str]
    # The company's tools as saved.
    tools: ToolsState = ToolsState()
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OrgUserCreate(BaseModel):
    """A company admin creating one of its users (always a viewer of its own company)."""

    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)
    full_name: Optional[str] = Field(None, max_length=128)
    email: Optional[EmailStr] = None
    # The views the new user starts with (radar codes, or ["*"]); they must fit inside the company's list. Omitted:
    # a copy of the company's list, as before.
    radar_detail_view: Optional[List[RadarResource]] = Field(None, max_length=500)
    # The tools the new user starts with; they must fit inside the company's. Omitted: a copy of the company's.
    tools: Optional[ToolsUpdate] = None

    @field_validator("username")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().lower()


class OrgUserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=128)
    email: Optional[EmailStr] = None
    # Kept only so the endpoint can REFUSE it (403): a company admin does not activate or deactivate accounts.
    is_active: Optional[bool] = None
