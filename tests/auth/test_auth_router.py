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
