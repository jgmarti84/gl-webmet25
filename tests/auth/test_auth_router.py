# tests/auth/test_auth_router.py
from api.app.auth.cookies import access_cookie_name, refresh_cookie_name

from .conftest import TEST_PASSWORD, login


def test_login_sets_cookies_and_returns_me(client, make_user):
    make_user(full_name="Alice A.")
    response = login(client)
    body = response.json()
    assert body["username"] == "alice" and body["role"] == "viewer"
    assert "password_hash" not in body
    assert access_cookie_name() in response.cookies
    assert refresh_cookie_name() in response.cookies
    set_cookie = response.headers.get_list("set-cookie")
    assert all("HttpOnly" in c for c in set_cookie)
    assert all("SameSite=strict" in c or "SameSite=Strict" in c for c in set_cookie)


def test_login_wrong_password_generic_401(client, make_user):
    make_user()
    response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong-password-xx"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o contraseña incorrectos"


def test_login_unknown_user_same_message(client):
    response = client.post("/api/v1/auth/login", json={"username": "nobody", "password": TEST_PASSWORD})
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o contraseña incorrectos"


def test_me_requires_session(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_after_login(client, make_user):
    make_user()
    login(client)
    assert client.get("/api/v1/auth/me").json()["username"] == "alice"


def test_refresh_rotates_cookie(client, make_user):
    make_user()
    login(client)
    old_refresh = client.cookies.get(refresh_cookie_name())
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert client.cookies.get(refresh_cookie_name()) != old_refresh


def test_refresh_without_cookie_401(client):
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_race_returns_code(client, make_user):
    make_user()
    login(client)
    old_refresh = client.cookies.get(refresh_cookie_name())
    client.post("/api/v1/auth/refresh")
    # Simulate a second tab still holding the previous refresh cookie.
    client.cookies.clear()
    client.cookies.set(refresh_cookie_name(), old_refresh)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == "refresh_race"


def test_logout_clears_session(client, make_user):
    make_user()
    login(client)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_bad_origin_is_rejected(client, make_user):
    make_user()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": TEST_PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_allowed_origin_is_accepted(client, make_user):
    make_user()
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": TEST_PASSWORD},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200


def test_deactivated_user_loses_access_immediately(client, make_user, test_db_session):
    user = make_user()
    login(client)
    user.is_active = False
    user.token_version += 1
    test_db_session.flush()
    assert client.get("/api/v1/auth/me").status_code == 401


def _set_cookie_header(response, cookie_name):
    """The Set-Cookie header the response sends for `cookie_name`."""
    return next(c for c in response.headers.get_list("set-cookie") if c.startswith(f"{cookie_name}="))


def test_refresh_cookie_is_scoped_to_the_auth_path(client, make_user):
    make_user()
    response = login(client)
    assert "Path=/api/v1/auth" in _set_cookie_header(response, refresh_cookie_name())
    assert "Path=/;" in _set_cookie_header(response, access_cookie_name()) + ";"


def test_logout_expires_both_cookies(client, make_user):
    make_user()
    login(client)
    response = client.post("/api/v1/auth/logout")
    for name in (access_cookie_name(), refresh_cookie_name()):
        assert "max-age=0" in _set_cookie_header(response, name).lower()


def test_old_refresh_copy_is_rejected_after_logout(client, make_user):
    make_user()
    login(client)
    kept_copy = client.cookies.get(refresh_cookie_name())
    client.post("/api/v1/auth/logout")
    # Somebody kept a copy of the refresh cookie and replays it after the logout.
    client.cookies.clear()
    client.cookies.set(refresh_cookie_name(), kept_copy)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json().get("code") != "refresh_race"


def test_refresh_response_matches_the_me_contract(client, make_user):
    make_user(full_name="Alice A.")
    login(client)
    body = client.post("/api/v1/auth/refresh").json()
    assert set(body) == {"id", "username", "full_name", "role", "password_is_bootstrap", "access_expires_in"}
    assert isinstance(body["id"], int)
    assert body["username"] == "alice" and body["full_name"] == "Alice A."
    assert body["role"] == "viewer"
    assert isinstance(body["password_is_bootstrap"], bool)


def test_login_and_refresh_report_the_full_access_lifetime(client, make_user):
    from api.app.config import settings

    make_user()
    full = settings.access_token_ttl_minutes * 60
    assert login(client).json()["access_expires_in"] == full
    assert client.post("/api/v1/auth/refresh").json()["access_expires_in"] == full


def test_me_reports_the_remaining_access_lifetime(client, make_user):
    from api.app.config import settings

    make_user()
    login(client)
    remaining = client.get("/api/v1/auth/me").json()["access_expires_in"]
    assert 0 < remaining <= settings.access_token_ttl_minutes * 60


def test_full_session_flow_opens_and_closes_the_admin_api(client, make_user):
    make_user(username="boss", role="admin")
    assert client.get("/api/v1/admin/radars").status_code == 401
    login(client, username="boss")
    assert client.get("/api/v1/admin/radars").status_code == 200
    assert client.post("/api/v1/auth/refresh").status_code == 200
    assert client.get("/api/v1/admin/radars").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/admin/radars").status_code == 401


def test_check_without_session_is_401(client):
    assert client.get("/api/v1/auth/check").status_code == 401


def test_check_with_session_is_204_without_body(client, make_user):
    make_user()
    login(client)
    response = client.get("/api/v1/auth/check")
    assert response.status_code == 204
    assert response.content == b""


def test_check_admin_role_rejects_a_viewer(client, make_user):
    make_user()
    login(client)
    assert client.get("/api/v1/auth/check", params={"role": "admin"}).status_code == 403


def test_check_admin_role_accepts_an_admin(client, make_user):
    make_user(username="boss", role="admin")
    login(client, username="boss")
    assert client.get("/api/v1/auth/check", params={"role": "admin"}).status_code == 204


def test_check_unknown_role_is_422(client, make_user):
    make_user()
    login(client)
    assert client.get("/api/v1/auth/check", params={"role": "superuser"}).status_code == 422


# /auth/check-token: the light probe of the basemap tile proxies. It trusts the signed JWT alone and never
# reads the user, so moving the map costs no database connection.


def test_check_token_without_session_is_401(client):
    assert client.get("/api/v1/auth/check-token").status_code == 401


def test_check_token_with_session_is_204_without_body(client, make_user):
    make_user()
    login(client)
    response = client.get("/api/v1/auth/check-token")
    assert response.status_code == 204
    assert response.content == b""


def test_check_token_with_a_tampered_token_is_401(client, make_user):
    make_user()
    login(client)
    token = client.cookies.get(access_cookie_name())
    # Change one character inside the signature: same shape, wrong signature. Not the last one: its two
    # lowest bits are base64 padding, so some changes there decode to the very same signature.
    tampered = token[:-5] + ("A" if token[-5] != "A" else "B") + token[-4:]
    # Clear first: the login cookie carries the server's domain, so set() alone would add a second
    # cookie with the same name and the request would still send the good one.
    client.cookies.clear()
    client.cookies.set(access_cookie_name(), tampered)
    assert client.get("/api/v1/auth/check-token").status_code == 401


def test_check_token_with_an_expired_token_is_401(client, make_user):
    from datetime import datetime, timedelta, timezone

    from api.app.auth.security import create_access_token

    user = make_user()
    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    client.cookies.set(access_cookie_name(), create_access_token(user.id, user.role, user.token_version, two_hours_ago))
    assert client.get("/api/v1/auth/check-token").status_code == 401


def test_check_token_never_opens_a_database_session(client, make_user):
    from radar_db import get_db

    make_user()
    login(client)

    def no_database():
        raise AssertionError("/auth/check-token must not ask for a database session")
        yield  # never reached: makes this a generator, like get_db

    client.app.dependency_overrides[get_db] = no_database
    assert client.get("/api/v1/auth/check-token").status_code == 204


def test_check_token_keeps_a_deactivated_user_until_the_token_expires(client, make_user, test_db_session):
    """Accepted trade-off: the light probe does not see a deactivation; the full probe does, at once.

    The light probe only guards public basemap tiles, and the access token lives 30 minutes at most.
    """
    user = make_user()
    login(client)
    user.is_active = False
    user.token_version += 1
    test_db_session.flush()
    assert client.get("/api/v1/auth/check-token").status_code == 204
    assert client.get("/api/v1/auth/check").status_code == 401


def test_login_with_the_e_mail(client, make_user):
    make_user(email="ana@ejemplo.com.ar")
    response = client.post("/api/v1/auth/login", json={"username": "ana@ejemplo.com.ar", "password": TEST_PASSWORD})
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_login_with_an_unverified_mail_says_so_only_with_the_right_password(client, make_user):
    make_user(username="pend", email="pend@ejemplo.com.ar", email_verified=False)
    right = client.post("/api/v1/auth/login", json={"username": "pend", "password": TEST_PASSWORD})
    assert right.status_code == 403
    assert right.json()["code"] == "email_not_verified"
    assert not right.cookies
    wrong = client.post("/api/v1/auth/login", json={"username": "pend", "password": "wrong-password-xx"})
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Usuario o contraseña incorrectos"
