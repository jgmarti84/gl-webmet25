# tests/auth/conftest.py
import re

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
def client(test_db_session):
    """FastAPI app with the auth routers, using the test database session."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.app.routers.admin import router as admin_router
    from api.app.routers.auth import router as auth_router
    from api.app.routers.users import router as users_router
    from radar_db import get_db

    app = FastAPI()
    for router in (auth_router, users_router, admin_router):
        app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: test_db_session
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


def login(client, username="alice", password=TEST_PASSWORD):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response


@pytest.fixture
def app_client(test_db_session):
    """The real application (every router, as wired in main.py), using the test database session.

    The lifespan (Redis, GDAL, admin check) does not run: the client is not used as a context manager.
    """
    from fastapi.testclient import TestClient

    from api.app.main import app
    from radar_db import get_db

    app.dependency_overrides[get_db] = lambda: test_db_session
    try:
        yield TestClient(app, base_url="http://testserver")
    finally:
        app.dependency_overrides.pop(get_db, None)


# --- public registration (spec B) ----------------------------------------------

TEST_EMAIL_DOMAIN = "ejemplo.com.ar"


@pytest.fixture
def mailer():
    """Collects the mails the API would send."""
    from api.app.mail.service import FakeMailer

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
