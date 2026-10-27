# api/app/schemas/auth.py
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .text import StrictText


class LoginRequest(StrictText):
    # Username or e-mail (an e-mail can be up to 254 characters).
    username: str = Field(..., min_length=1, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class MeResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    role: str
    password_is_bootstrap: bool
    # Seconds until the current access token expires; the frontend renews the session before that.
    access_expires_in: int


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)
    role: Literal["admin", "viewer"]
    full_name: Optional[str] = Field(None, max_length=128)
    email: Optional[str] = Field(None, max_length=254)

    @field_validator("username")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().lower()


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=128)
    email: Optional[str] = Field(None, max_length=254)
    role: Optional[Literal["admin", "viewer"]] = None
    is_active: Optional[bool] = None


class PasswordReset(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str
    is_active: bool
    password_is_bootstrap: bool
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
