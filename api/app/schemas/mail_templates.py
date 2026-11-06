# api/app/schemas/mail_templates.py
"""Bodies and answers of the mail text endpoints (spec F)."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .text import StrictText


class MailTextsBody(StrictText):
    """The six texts of a mail, all required. A field that is missing or that does not belong here is a 422: nobody
    can send `key` or `updated_by` in the body. The limits repeat the ones of the table; the service checks the
    rest (empty after trimming, line breaks, markers, paragraphs)."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(..., max_length=150)
    heading: str = Field(..., max_length=120)
    body: str = Field(..., max_length=2000)
    button: str = Field(..., max_length=40)
    footer: str = Field(..., max_length=400)
    fallback: str = Field(..., max_length=200)


class Placeholder(BaseModel):
    name: str
    example: str


class MailTemplateResponse(BaseModel):
    """One mail as the admin screen shows it: the text in use, the original, and the markers it accepts."""

    key: str
    title: str
    customized: bool
    texts: Dict[str, str]
    defaults: Dict[str, str]
    placeholders: List[Placeholder]
    updated_at: Optional[datetime] = None
    updated_by_username: Optional[str] = None


class MailPreviewResponse(BaseModel):
    subject: str
    # The whole mail as HTML, to show inside a sandboxed iframe (the page never injects it into its own DOM).
    html: str
