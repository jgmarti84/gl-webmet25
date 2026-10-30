# tests/auth/conftest.py
import re
from concurrent.futures import Future

import pytest

from radar_db.accounts import create_user

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def make_user(test_db_session):
    """Factory that creates a user inside the rolled-back test transaction."""

    def _make(username="alice", role="viewer", password=TEST_PASSWORD, **kwargs):
        user = create_user(test_db_session, username=username, password=password, role=role, **kwargs)
        test_db_session.flush()
        return user

    return _make


@pytest.fixture
def google_verifier():
    """Stands in for Google: the test sets `.identity` (what a valid token carries) or `.fail = True`."""
    from api.app.auth.google import FakeGoogleVerifier

    return FakeGoogleVerifier()


@pytest.fixture
def google_on(monkeypatch):
    """"Sign in with Google" configured (an OAuth client ID is set)."""
    from api.app.config import settings

    monkeypatch.setattr(settings, "google_client_id", "123-test.apps.googleusercontent.com")


@pytest.fixture
def client(test_db_session, mailer, google_verifier):
    """FastAPI app with the auth routers, using the test database session, a fake mailer and a fake Google."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.app.auth.google import get_google_verifier
    from api.app.mail.service import get_mailer
    from api.app.routers.admin import router as admin_router
    from api.app.routers.auth import router as auth_router
    from api.app.routers.registration import router as registration_router
    from api.app.routers.users import router as users_router
    from radar_db import get_db

    app = FastAPI()
    for router in (auth_router, registration_router, users_router, admin_router):
        app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_mailer] = lambda: mailer
    app.dependency_overrides[get_google_verifier] = lambda: google_verifier
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


def login(client, username="alice", password=TEST_PASSWORD):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response


@pytest.fixture
def app_client(test_db_session, mailer):
    """The real application (every router, as wired in main.py), using the test database session.

    The lifespan (Redis, GDAL, admin check) does not run: the client is not used as a context manager.
    """
    from fastapi.testclient import TestClient

    from api.app.mail.service import get_mailer
    from api.app.main import app
    from radar_db import get_db

    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_mailer] = lambda: mailer
    try:
        yield TestClient(app, base_url="http://testserver")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_mailer, None)


# --- public registration (spec B) ----------------------------------------------

TEST_EMAIL_DOMAIN = "ejemplo.com.ar"


class _InlineExecutor:
    """Runs each queued send right away, so a test sees the mail as soon as the request returns.

    The API sends from its own mail threads (api/app/mail/service.py); here that would race with the assertions.
    The tests of the mail threads themselves (test_mail.py) use the real pool.
    """

    def submit(self, fn, *args):
        future = Future()
        fn(*args)
        future.set_result(None)
        return future


@pytest.fixture
def mailer(monkeypatch):
    """Collects the mails the API would send (sent at once, in the request's own thread)."""
    from api.app.mail import service
    from api.app.mail.service import FakeMailer

    monkeypatch.setattr(service, "_mail_executor", _InlineExecutor())
    return FakeMailer()


@pytest.fixture
def registration_on(monkeypatch):
    """Mail and registration fully configured."""
    from api.app.config import settings

    values = dict(
        registration_enabled=True,
        public_base_url="https://webmet.test",
        mail_host="smtp.test",
        mail_from=f"no-reply@{TEST_EMAIL_DOMAIN}",
        # The "with terms" setup: tests of the default (no terms) turn this off themselves.
        terms_required=True,
        terms_url="https://webmet.test/terminos",
        privacy_url="https://webmet.test/privacidad",
    )
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


def register_payload(**overrides):
    """Body of POST /auth/register with valid values; tests override the field they are checking."""
    payload = {
        "username": "nuevo",
        "email": f"nuevo@{TEST_EMAIL_DOMAIN}",
        "password": TEST_PASSWORD,
        "accept_terms": True,
        "website": "",
    }
    payload.update(overrides)
    return payload


def token_from(mail) -> str:
    """The token inside the link of a mail."""
    return re.search(r"token=([A-Za-z0-9_-]{43})", mail.text).group(1)
