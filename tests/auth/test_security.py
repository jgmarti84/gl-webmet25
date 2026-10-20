# tests/auth/test_security.py
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from api.app.auth.security import (
    ALGORITHM,
    InvalidAccessToken,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
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


def test_refresh_token_is_random_and_hash_is_stable():
    a, b = generate_refresh_token(), generate_refresh_token()
    assert a != b and len(a) >= 40
    assert hash_refresh_token(a) == hash_refresh_token(a)
    assert len(hash_refresh_token(a)) == 64
