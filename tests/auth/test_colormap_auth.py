# tests/auth/test_colormap_auth.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .conftest import login


@pytest.fixture
def cmap_client(test_db_session):
    from api.app.routers.auth import router as auth_router
    from api.app.routers.colormap import router as colormap_router
    from radar_db import get_db

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(colormap_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: test_db_session
    with TestClient(app, base_url="http://testserver") as c:
        yield c


def test_invalidate_requires_admin(cmap_client, make_user):
    assert cmap_client.post("/api/v1/colormap/cache/invalidate").status_code == 401
    make_user(username="boss", role="admin")
    login(cmap_client, "boss")
    assert cmap_client.post("/api/v1/colormap/cache/invalidate").status_code == 200
