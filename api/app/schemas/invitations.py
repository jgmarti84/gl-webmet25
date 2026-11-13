# api/app/schemas/invitations.py
"""Bodies and answers of the invitation endpoint."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from .permissions import RadarResource, ToolsUpdate
from .registration import MAX_EMAIL_LENGTH, MAX_TOKEN_FIELD_LENGTH
from .text import StrictText


class _InvitedMail(StrictText):
    """Body with the invited mail, validated like the sign-up one (format and length of the column)."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _short_enough(cls, value: str) -> str:
        if len(value) > MAX_EMAIL_LENGTH:
            raise ValueError("El mail es demasiado largo")
        return value


class OrgInvitationCreate(_InvitedMail):
    """An institution admin inviting a viewer to its own institution: no institution and no role to choose."""

    # Radar codes (or ["*"]). Omitted: the person starts with a copy of the institution's list.
    radar_views: Optional[List[RadarResource]] = Field(None, max_length=500)
    # The tools the person starts with (only for a viewer). Omitted, or the tool left out: a copy of the institution's
    # tools when the invitation is accepted.
    tools: Optional[ToolsUpdate] = None


class InvitationCreate(OrgInvitationCreate):
    """The general admin inviting: any institution, institution admin or viewer."""

    organization_id: int
    role: Literal["org_admin", "viewer"]


class InvitationResponse(BaseModel):
    """An invitation as the inviter sees it. The token is never here: it only travels in the mail."""

    id: UUID
    email: str
    organization_id: int
    organization_name: str
    role: str
    radar_views: Optional[List[str]] = None
    # The tool choices of the invitation (a tool left null is "a copy of the institution's"), or None when there
    # are none.
    tools: Optional[ToolsUpdate] = None
    created_at: datetime
    expires_at: datetime
    # The mail already has an account (worked out when asked, not stored), and, for the general admin only, the
    # name of the institution that account is in and would leave by accepting.
    existing_account: bool = False
    leaves_organization: Optional[str] = None


class InvitationToken(StrictText):
    """The token of a link. No minimum and a generous maximum on purpose: the exact format is checked by the service,
    and every wrong token (empty, short, invented) gets the same 404 as an expired one."""

    token: str = Field(..., max_length=MAX_TOKEN_FIELD_LENGTH)


class InvitationDetails(BaseModel):
    """What the page shows before the person creates the account."""

    organization_name: str
    email: str
    role: str
    google_available: bool
    # The mail has an account: the page shows the login instead of the sign-up form.
    account_exists: bool = False


class AcceptInvitation(InvitationToken):
    # Same limits as the sign-up form: the username shape and the password policy are checked by the service.
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)
    full_name: Optional[str] = Field(None, max_length=128)
    # Must be true only when the site asks for the terms (TERMS_REQUIRED).
    accept_terms: bool = False


class AcceptInvitationGoogle(InvitationToken):
    # The ID token Google gives the browser (about 1 to 2 KB).
    credential: str = Field(..., min_length=1, max_length=4096)
