# api/app/auth/google.py
"""Checking the token Google gives the browser after "Sign in with Google".

The browser shows the Google button and the choice of account; Google answers with an ID token: a signed text that
says who the person is. Nothing in it can be trusted until the signature is checked, and that is done here with
the public keys Google publishes (downloaded over HTTPS and kept in memory by PyJWKClient, so a login does not
call Google each time). No secret is involved and nothing about the person is sent to Google.

Routers depend on get_google_verifier(); tests replace it with FakeGoogleVerifier.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

import jwt

from ..config import settings

logger = logging.getLogger(__name__)

# Where Google publishes the public keys that sign its ID tokens, and the two spellings of its issuer name.
GOOGLE_KEYS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
# The clocks of this server and Google's may differ a little; a token is not refused for a few seconds of it.
CLOCK_SKEW_SECONDS = 10


@dataclass(frozen=True)
class GoogleIdentity:
    """What the API uses from a verified token."""

    sub: str  # fixed identifier of the Google account (never changes, unlike the mail)
    email: str
    email_verified: bool  # whether Google itself confirmed that the person owns this mail
    name: Optional[str] = None


class GoogleTokenError(Exception):
    """The token is not valid: forged, expired, for another application, or not readable."""


class GoogleVerifier(Protocol):
    def verify(self, credential: str) -> GoogleIdentity: ...


class GoogleIdTokenVerifier:
    """Verifies a Google ID token: signature (RS256, Google's keys), issuer, audience (our client ID) and expiry."""

    def __init__(self) -> None:
        # Keeps the downloaded keys for an hour and looks a key up by the "kid" the token names.
        self._keys = jwt.PyJWKClient(GOOGLE_KEYS_URL, cache_keys=True, lifespan=3600, timeout=10)

    def verify(self, credential: str) -> GoogleIdentity:
        try:
            signing_key = self._keys.get_signing_key_from_jwt(credential)
            claims = jwt.decode(
                credential,
                signing_key.key,
                algorithms=["RS256"],  # never what the token header asks for: a forged "none" or HS256 is refused
                audience=settings.google_client_id,  # the token must have been issued for OUR application
                issuer=list(GOOGLE_ISSUERS),
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            # Only the class name: the text of the error can carry parts of the token.
            raise GoogleTokenError(f"Google: {exc.__class__.__name__}") from exc
        email = claims.get("email")
        if not email:
            raise GoogleTokenError("Google: sin mail")
        return GoogleIdentity(
            sub=str(claims["sub"]),
            email=str(email),
            email_verified=claims.get("email_verified") is True,
            name=claims.get("name"),
        )


class FakeGoogleVerifier:
    """Answers with the identity a test sets, or fails like an invalid token (tests)."""

    def __init__(self) -> None:
        self.identity: Optional[GoogleIdentity] = None
        self.fail = False

    def verify(self, credential: str) -> GoogleIdentity:
        if self.fail or self.identity is None:
            raise GoogleTokenError("Google: token inválido")
        return self.identity


_verifier = GoogleIdTokenVerifier()


def get_google_verifier() -> GoogleVerifier:
    """FastAPI dependency; tests override it with a FakeGoogleVerifier."""
    return _verifier
