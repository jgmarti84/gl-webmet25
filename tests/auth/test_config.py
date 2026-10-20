# tests/auth/test_config.py
import pytest
from pydantic import ValidationError

from api.app.config import APISettings

GOOD_SECRET = "s" * 40


def test_short_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        APISettings(_env_file=None, JWT_SECRET="too-short")


def test_allowed_origins_list_parsing():
    s = APISettings(_env_file=None, JWT_SECRET=GOOD_SECRET, ALLOWED_ORIGINS=" http://a , http://b ,")
    assert s.allowed_origins_list == ["http://a", "http://b"]


def test_cors_defaults_to_allowed_origins():
    s = APISettings(_env_file=None, JWT_SECRET=GOOD_SECRET, ALLOWED_ORIGINS="http://a", CORS_ORIGINS="")
    assert s.cors_origins_list == ["http://a"]


AUTH_ENV_VARS = (
    "ACCESS_TOKEN_TTL_MINUTES",
    "SESSION_IDLE_TTL_HOURS",
    "SESSION_ABSOLUTE_TTL_DAYS",
    "COOKIE_SECURE",
    "LOGIN_MAX_FAILED_ATTEMPTS",
    "LOGIN_LOCKOUT_MINUTES",
)


def test_auth_defaults(monkeypatch):
    # The tests container sets COOKIE_SECURE=false; defaults must be checked without it.
    for name in AUTH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    s = APISettings(_env_file=None, JWT_SECRET=GOOD_SECRET)
    assert s.access_token_ttl_minutes == 15
    assert s.session_idle_ttl_hours == 48
    assert s.session_absolute_ttl_days == 7
    assert s.cookie_secure is True
    assert s.login_max_failed_attempts == 5
    assert s.login_lockout_minutes == 15
