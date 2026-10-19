# tests/auth/conftest.py
import pytest

from radar_db.accounts import create_user

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture
def make_user(test_db_session):
    """Factory that creates a user inside the rolled-back test transaction."""
    def _make(username="alice", role="viewer", password=TEST_PASSWORD, **kwargs):
        user = create_user(
            test_db_session, username=username, password=password, role=role, **kwargs
        )
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
