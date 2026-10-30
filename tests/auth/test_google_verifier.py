# tests/auth/test_google_verifier.py
"""The real check of a Google ID token (api/app/auth/google.py), without calling Google.

The tests sign tokens with a key pair made here and hand the public half to the verifier, in place of the keys Google
publishes. What is under test is the part that decides whether a token is believed: signature, algorithm, audience,
issuer and expiry.
"""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from api.app.auth.google import GoogleIdTokenVerifier, GoogleTokenError

CLIENT_ID = "123-test.apps.googleusercontent.com"
ISSUER = "https://accounts.google.com"


@pytest.fixture(scope="module")
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


@pytest.fixture
def verifier(keys, monkeypatch):
    from api.app.config import settings

    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    instance = GoogleIdTokenVerifier()
    # The keys Google would publish: here, the public half of the pair made above.
    monkeypatch.setattr(instance._keys, "get_signing_key_from_jwt", lambda token: SimpleNamespace(key=keys[1]))
    return instance


def _token(private, **claims):
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "g-100",
        "email": "ana@gmail.com",
        "email_verified": True,
        "name": "Ana Pérez",
        "iat": now,
        "exp": now + 600,
    }
    payload.update(claims)
    return jwt.encode({k: v for k, v in payload.items() if v is not None}, private, algorithm="RS256")


def test_a_valid_token_gives_the_identity(verifier, keys):
    identity = verifier.verify(_token(keys[0]))
    assert (identity.sub, identity.email, identity.email_verified, identity.name) == (
        "g-100",
        "ana@gmail.com",
        True,
        "Ana Pérez",
    )


def test_the_other_spelling_of_the_issuer_is_accepted(verifier, keys):
    assert verifier.verify(_token(keys[0], iss="accounts.google.com")).sub == "g-100"


def test_a_token_for_another_application_is_refused(verifier, keys):
    with pytest.raises(GoogleTokenError):
        verifier.verify(_token(keys[0], aud="999-other.apps.googleusercontent.com"))


def test_a_token_from_another_issuer_is_refused(verifier, keys):
    with pytest.raises(GoogleTokenError):
        verifier.verify(_token(keys[0], iss="https://evil.example"))


def test_an_expired_token_is_refused(verifier, keys):
    with pytest.raises(GoogleTokenError):
        verifier.verify(_token(keys[0], exp=int(time.time()) - 3600, iat=int(time.time()) - 7200))


def test_a_token_signed_with_another_key_is_refused(verifier):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(GoogleTokenError):
        verifier.verify(_token(other))


def test_an_unsigned_token_is_refused(verifier):
    forged = jwt.encode(
        {"iss": ISSUER, "aud": CLIENT_ID, "sub": "g-1", "email": "a@b.com", "exp": 9999999999}, None, algorithm="none"
    )
    with pytest.raises(GoogleTokenError):
        verifier.verify(forged)


def test_a_token_missing_a_required_claim_is_refused(verifier, keys):
    with pytest.raises(GoogleTokenError):
        verifier.verify(_token(keys[0], sub=None))


def test_a_token_without_a_mail_is_refused(verifier, keys):
    with pytest.raises(GoogleTokenError):
        verifier.verify(_token(keys[0], email=None))


def test_email_verified_must_be_exactly_true(verifier, keys):
    assert verifier.verify(_token(keys[0], email_verified=False)).email_verified is False
    assert (
        verifier.verify(_token(keys[0], email_verified="true")).email_verified is False
    )  # not a boolean: not believed


def test_garbage_is_refused(verifier):
    with pytest.raises(GoogleTokenError):
        verifier.verify("not-a-token")
