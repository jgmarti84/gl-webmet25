# api/app/schemas/organizations.py
"""Bodies of the company endpoints (spec C): /admin/organizations and /org."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    seat_limit: int = Field(..., gt=0, le=10000)
    is_active: bool = True

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
    is_active: bool
    # The company's list as saved: radar codes, or ["*"].
    radar_detail_views: List[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OrgUserCreate(BaseModel):
    """A company admin creating one of its users (always a viewer of its own company)."""

    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)
    full_name: Optional[str] = Field(None, max_length=128)
    email: Optional[EmailStr] = None

    @field_validator("username")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().lower()


class OrgUserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=128)
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
