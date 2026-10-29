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
    assert s.access_token_ttl_minutes == 30
    assert s.session_idle_ttl_hours == 48
    assert s.session_absolute_ttl_days == 7
    assert s.cookie_secure is True
    assert s.login_max_failed_attempts == 5
    assert s.login_lockout_minutes == 15


MAIL_ENV_VARS = (
    "REGISTRATION_ENABLED",
    "PUBLIC_BASE_URL",
    "MAIL_HOST",
    "MAIL_PORT",
    "MAIL_USER",
    "MAIL_PASSWORD",
    "MAIL_FROM",
    "MAIL_STARTTLS",
    "MAIL_USE_SSL",
    "TERMS_REQUIRED",
    "TERMS_URL",
    "PRIVACY_URL",
    "EMAIL_VERIFY_TTL_HOURS",
    "PASSWORD_RESET_TTL_MINUTES",
    "MAIL_MAX_PER_HOUR",
    "MAIL_MIN_INTERVAL_SECONDS",
)


def _clean_settings(monkeypatch, **values):
    # The dev stack sets some of these in the API container; the tests container must not leak them.
    for name in MAIL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return APISettings(_env_file=None, JWT_SECRET=GOOD_SECRET, **values)


def test_mail_defaults(monkeypatch):
    s = _clean_settings(monkeypatch)
    assert s.registration_enabled is False
    assert s.terms_required is False
    assert s.mail_port == 587
    assert s.mail_starttls is True
    assert s.mail_use_ssl is False
    assert s.email_verify_ttl_hours == 24
    assert s.password_reset_ttl_minutes == 60
    assert s.mail_max_per_hour == 3
    assert s.mail_min_interval_seconds == 60
    assert s.mail_configured is False
    assert s.registration_available is False


def test_mail_configured_needs_host_sender_and_base_url(monkeypatch):
    full = dict(MAIL_HOST="smtp.test", MAIL_FROM="no-reply@ejemplo.com.ar", PUBLIC_BASE_URL="https://webmet.test")
    assert _clean_settings(monkeypatch, **full).mail_configured is True
    for missing in full:
        partial = {k: v for k, v in full.items() if k != missing}
        assert _clean_settings(monkeypatch, **partial).mail_configured is False, missing


SIGN_UP_BASE = dict(
    REGISTRATION_ENABLED=True,
    MAIL_HOST="smtp.test",
    MAIL_FROM="no-reply@ejemplo.com.ar",
    PUBLIC_BASE_URL="https://webmet.test",
)
LEGAL_LINKS = dict(TERMS_URL="https://webmet.test/terminos", PRIVACY_URL="https://webmet.test/privacidad")


def test_registration_needs_the_switch_and_the_mail(monkeypatch):
    assert _clean_settings(monkeypatch, **SIGN_UP_BASE).registration_available is True
    for missing in SIGN_UP_BASE:
        partial = {k: v for k, v in SIGN_UP_BASE.items() if k != missing}
        assert _clean_settings(monkeypatch, **partial).registration_available is False, missing


def test_the_terms_are_not_required_by_default(monkeypatch):
    # Without TERMS_REQUIRED the form asks for nothing, so the legal links are not needed to open the sign-up.
    s = _clean_settings(monkeypatch, **SIGN_UP_BASE)
    assert s.terms_required is False
    assert s.registration_available is True


def test_when_the_terms_are_required_both_links_are_needed(monkeypatch):
    full = dict(SIGN_UP_BASE, TERMS_REQUIRED=True, **LEGAL_LINKS)
    assert _clean_settings(monkeypatch, **full).registration_available is True
    for missing in LEGAL_LINKS:
        partial = {k: v for k, v in full.items() if k != missing}
        assert _clean_settings(monkeypatch, **partial).registration_available is False, missing


def test_registration_warnings(monkeypatch):
    def warnings(**values):
        return _clean_settings(monkeypatch, **values).registration_warnings

    # Off: nothing to say.
    assert warnings() == []
    # On but incomplete: says what is missing, and the sign-up stays off.
    assert any("MAIL_HOST" in w for w in warnings(REGISTRATION_ENABLED=True))
    assert any("TERMS_URL" in w for w in warnings(**dict(SIGN_UP_BASE, TERMS_REQUIRED=True)))
    # On and complete but without terms (the default): a reminder, because people would sign up accepting nothing.
    assert any("TERMS_REQUIRED" in w for w in warnings(**SIGN_UP_BASE))
    # On, complete and with the terms: all good.
    assert warnings(**dict(SIGN_UP_BASE, TERMS_REQUIRED=True, **LEGAL_LINKS)) == []
