# tests/auth/test_base_path_cookies.py
"""Auth cookies behind a proxy prefix (spec base-path §6). The test stack runs with COOKIE_SECURE=false, so the
names carry no __Host-/__Secure- prefix here.

The proxy strips the prefix before the API, so requests still go to /api/v1/...; only the X-Forwarded-Prefix
header changes. Cookies scoped to /nacho/api/v1/auth are not sent by the test client to /api/v1/auth, so these
tests clear its jar and send the Cookie header by hand, as the browser would through the proxy.
"""

from http.cookies import SimpleCookie

from starlette.requests import Request

from api.app.auth.cookies import access_cookie_name, refresh_cookie_name, request_base_path

from .conftest import TEST_PASSWORD

PFX = {"X-Forwarded-Prefix": "/nacho"}
LOGIN = {"username": "alice", "password": TEST_PASSWORD}


def _request(prefix: str) -> Request:
    return Request({"type": "http", "headers": [(b"x-forwarded-prefix", prefix.encode())]})


def _cookies(response) -> SimpleCookie:
    """Every Set-Cookie of the response, parsed (name -> morsel with value and path)."""
    jar = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        jar.load(header)
    return jar


def test_the_prefix_is_read_and_validated():
    assert request_base_path(_request("/nacho")) == "/nacho"
    for bad in ("", "/", "nacho", "/a/b", "/<x>", "/nacho/", '/"x'):
        assert request_base_path(_request(bad)) == ""


def test_names_without_and_with_prefix():
    assert access_cookie_name() == "webmet_access" and refresh_cookie_name() == "webmet_refresh"
    assert access_cookie_name("/nacho") == "nacho_webmet_access"
    assert refresh_cookie_name("/nacho") == "nacho_webmet_refresh"


def test_login_behind_a_prefix_sets_prefixed_cookies(client, make_user):
    make_user()
    jar = _cookies(client.post("/api/v1/auth/login", json=LOGIN, headers=PFX))
    assert jar["nacho_webmet_access"]["path"] == "/"
    assert jar["nacho_webmet_refresh"]["path"] == "/nacho/api/v1/auth"
    assert "webmet_access" not in jar


def test_an_invalid_prefix_keeps_todays_cookies(client, make_user):
    make_user()
    jar = _cookies(client.post("/api/v1/auth/login", json=LOGIN, headers={"X-Forwarded-Prefix": "/a/b"}))
    assert jar["webmet_access"]["path"] == "/"
    assert jar["webmet_refresh"]["path"] == "/api/v1/auth"


def test_a_prefixed_session_works_end_to_end(client, make_user):
    make_user()
    jar = _cookies(client.post("/api/v1/auth/login", json=LOGIN, headers=PFX))
    access = jar["nacho_webmet_access"].value
    refresh = jar["nacho_webmet_refresh"].value
    client.cookies.clear()

    me = client.get("/api/v1/auth/me", headers={**PFX, "Cookie": f"nacho_webmet_access={access}"})
    assert me.status_code == 200
    # The same cookie at the root (another copy of the site) is not a session there.
    assert client.get("/api/v1/auth/me", headers={"Cookie": f"nacho_webmet_access={access}"}).status_code == 401

    rotated = client.post("/api/v1/auth/refresh", headers={**PFX, "Cookie": f"nacho_webmet_refresh={refresh}"})
    assert rotated.status_code == 200
    assert _cookies(rotated)["nacho_webmet_refresh"]["path"] == "/nacho/api/v1/auth"

    new_refresh = _cookies(rotated)["nacho_webmet_refresh"].value
    out = client.post("/api/v1/auth/logout", headers={**PFX, "Cookie": f"nacho_webmet_refresh={new_refresh}"})
    assert out.status_code == 204
    cleared = _cookies(out)
    assert cleared["nacho_webmet_refresh"]["path"] == "/nacho/api/v1/auth"
    assert cleared["nacho_webmet_access"]["max-age"] == "0"


def test_the_light_probe_reads_the_prefixed_cookie(client, make_user):
    make_user()
    access = _cookies(client.post("/api/v1/auth/login", json=LOGIN, headers=PFX))["nacho_webmet_access"].value
    client.cookies.clear()
    headers = {**PFX, "Cookie": f"nacho_webmet_access={access}"}
    assert client.get("/api/v1/auth/check", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/check-token", headers=headers).status_code == 204
