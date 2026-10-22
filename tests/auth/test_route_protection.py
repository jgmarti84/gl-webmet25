# tests/auth/test_route_protection.py
"""Every route needs a session unless it is explicitly public (spec A, section 3).

The route list comes from the OpenAPI schema and every route is called WITHOUT a session: anything
that does not answer 401 is unprotected. Path parameters get dummy values; if a route were left
open, it would run against the rolled-back test database.
"""

import re

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from .conftest import login

PUBLIC_ROUTES = {
    ("get", "/health"),
    ("get", "/"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/refresh"),
    ("post", "/api/v1/auth/logout"),
}

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# Data routes without path parameters: a viewer must get past authentication on all of them.
VIEWER_READABLE = [
    "/api/v1/radars",
    "/api/v1/products",
    "/api/v1/cogs",
    "/api/v1/cogs/latest",
    "/api/v1/cogs/timeline",
    "/api/v1/tiles/cache/stats",
    "/api/v1/colormap/names",
    "/api/v1/colormap/options",
    "/api/v1/colormap/defaults",
    "/api/v1/tops-cores",
]


def declared_routes(client: TestClient) -> set:
    schema = client.get("/openapi.json").json()
    return {(method, path) for path, ops in schema["paths"].items() for method in ops if method in HTTP_METHODS}


def unprotected_routes(client: TestClient) -> list:
    """Routes that do not answer 401 without a session (public ones excluded)."""
    found = []
    for method, path in sorted(declared_routes(client) - PUBLIC_ROUTES):
        url = re.sub(r"\{[^}]+\}", "1", path)
        status = client.request(method, url).status_code
        if status != 401:
            found.append((method, path, status))
    return found


def test_every_route_requires_a_session_unless_public(app_client):
    assert unprotected_routes(app_client) == []


def test_public_routes_exist(app_client):
    assert PUBLIC_ROUTES <= declared_routes(app_client)


def test_the_check_detects_a_forgotten_router():
    router = APIRouter()

    @router.get("/api/v1/forgotten")
    def forgotten() -> dict:
        return {}

    app = FastAPI()
    app.include_router(router)
    assert unprotected_routes(TestClient(app)) == [("get", "/api/v1/forgotten", 200)]


def test_data_routes_reject_anonymous_requests(app_client):
    for path in VIEWER_READABLE:
        assert app_client.get(path).status_code == 401, path


def test_a_viewer_reads_every_data_route(app_client, make_user):
    make_user()
    login(app_client)
    for path in VIEWER_READABLE:
        assert app_client.get(path).status_code not in (401, 403), path


def test_a_viewer_cannot_use_admin_routes(app_client, make_user):
    make_user()
    login(app_client)
    assert app_client.get("/api/v1/admin/radars").status_code == 403
    assert app_client.get("/api/v1/admin/users").status_code == 403
    assert app_client.post("/api/v1/colormap/cache/invalidate").status_code == 403
