# api/app/schemas/registration.py
"""Bodies and answers of the public registration endpoints."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from .text import StrictText

# Longest valid e-mail address (RFC 5321); also the size of the users.email column.
MAX_EMAIL_LENGTH = 254
# Real tokens are 43 characters; anything this long is not a mistyped token but abuse.
MAX_TOKEN_FIELD_LENGTH = 4096


class _EmailField(StrictText):
    """Body with a validated e-mail (format by email-validator, plus the length of the column)."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _short_enough(cls, value: str) -> str:
        if len(value) > MAX_EMAIL_LENGTH:
            raise ValueError("El mail es demasiado largo")
        return value


class RegisterRequest(_EmailField):
    # Username shape (letters, digits, dot, dash, underscore) is checked by the service: it needs the same rule
    # the admin panel uses. Here only the size, to stop huge values early.
    username: str = Field(..., min_length=3, max_length=32)
    # The password policy (12 to 128 characters, not the username...) is checked by the service.
    password: str = Field(..., min_length=1, max_length=128)
    # Optional "Nombre y apellido" in a single field (same size as users.full_name). The service cleans it up
    # (white space, non-printable characters) and stores NULL when it ends up empty.
    full_name: Optional[str] = Field(None, max_length=128)
    # Must be true only when the server asks for the terms (TERMS_REQUIRED); otherwise the page does not send it.
    accept_terms: bool = False
    # Decoy: hidden in the form, a person never fills it. A bot that does is answered but ignored.
    website: str = Field("", max_length=256)


class ForgotPasswordRequest(_EmailField):
    pass


class TokenRequest(StrictText):
    # No minimum and a generous maximum on purpose: the exact format (43 URL-safe characters) is checked by the
    # service before any lookup, and every wrong token (empty, short, long, invented) must get the same 400 as
    # an expired link. A 422 here would tell apart "malformed" from "expired". The maximum only stops absurd bodies.
    token: str = Field(..., max_length=MAX_TOKEN_FIELD_LENGTH)


class IdentifierRequest(StrictText):
    # A username or an e-mail address.
    identifier: str = Field(..., min_length=1, max_length=254)


class ResetPasswordRequest(StrictText):
    token: str = Field(..., max_length=MAX_TOKEN_FIELD_LENGTH)  # same reasoning as TokenRequest
    password: str = Field(..., min_length=1, max_length=128)


class MessageResponse(BaseModel):
    detail: str


class OptionsResponse(BaseModel):
    """What the login page may offer: the "create account" and "forgot password" links, and the legal links."""

    registration: bool
    password_recovery: bool
    # When false the sign-up page shows no terms checkbox, and the two links below are null.
    terms_required: bool
    terms_url: Optional[str] = None
    privacy_url: Optional[str] = None
    # The Google OAuth client ID the login page needs to draw "Sign in with Google"; null when it is not set up.
    google_client_id: Optional[str] = None
