# tests/auth/test_security.py
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from api.app.auth.security import (
    ALGORITHM,
    InvalidAccessToken,
    build_refresh_token,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    parse_refresh_token,
)
from api.app.config import settings


def _payload(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "1",
        "role": "admin",
        "tv": 0,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": "x",
    }
    payload.update(overrides)
    return payload


def test_roundtrip():
    token = create_access_token(user_id=7, role="viewer", token_version=3)
    claims = decode_access_token(token)
    assert (claims.user_id, claims.role, claims.token_version) == (7, "viewer", 3)


def test_expired_token_is_rejected():
    token = create_access_token(1, "admin", 0, now=datetime.now(timezone.utc) - timedelta(hours=1))
    with pytest.raises(InvalidAccessToken):
        decode_access_token(token)


def test_wrong_signature_is_rejected():
    token = jwt.encode(_payload(), "another-secret-" + "x" * 30, algorithm=ALGORITHM)
    with pytest.raises(InvalidAccessToken):
        decode_access_token(token)


def test_alg_none_is_rejected():
    token = jwt.encode(_payload(), key="", algorithm="none")
    with pytest.raises(InvalidAccessToken):
        decode_access_token(token)


@pytest.mark.parametrize("claim,value", [("iss", "someone-else"), ("aud", "other-api")])
def test_wrong_issuer_or_audience_is_rejected(claim, value):
    token = jwt.encode(_payload(**{claim: value}), settings.jwt_secret, algorithm=ALGORITHM)
    with pytest.raises(InvalidAccessToken):
        decode_access_token(token)


def test_garbage_is_rejected():
    with pytest.raises(InvalidAccessToken):
        decode_access_token("not-a-jwt")


SESSION_ID = uuid.UUID("3f2a9c1e-5b7d-4e8f-9a0b-1c2d3e4f5a6b")
SECRET = "a" * 43


def test_refresh_token_carries_the_session_id():
    token = build_refresh_token(SESSION_ID)
    head, secret = token.split(".")
    assert head == str(SESSION_ID)
    assert len(secret) == 43
    assert parse_refresh_token(token) == SESSION_ID
    assert build_refresh_token(SESSION_ID) != token  # the secret is random


def test_refresh_token_hash_is_stable():
    token = build_refresh_token(SESSION_ID)
    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert len(hash_refresh_token(token)) == 64


@pytest.mark.parametrize(
    "token",
    [
        "",
        "garbage",
        "Xb3kQ9" * 7 + "A",  # old format: 43 URL-safe characters, no dot
        f"{SESSION_ID}.",
        f"{SESSION_ID}.{'a' * 42}",
        f"{SESSION_ID}.{'a' * 44}",
        f"{SESSION_ID}.{SECRET}.extra",
        f"{SESSION_ID.hex}.{SECRET}",
        f"{str(SESSION_ID).upper()}.{SECRET}",
        f"not-a-uuid.{SECRET}",
        f"{SESSION_ID}.{'a' * 42}!",
    ],
)
def test_malformed_refresh_tokens_do_not_parse(token):
    assert parse_refresh_token(token) is None


def test_well_formed_refresh_token_parses():
    assert parse_refresh_token(f"{SESSION_ID}.{SECRET}") == SESSION_ID
