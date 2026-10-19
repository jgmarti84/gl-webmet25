# tests/auth/test_users_router.py
import pytest

from radar_db.passwords import verify_password

from .conftest import TEST_PASSWORD, login

BASE = "/api/v1/admin/users"


def _as_admin(client, make_user, username="boss"):
    admin = make_user(username=username, role="admin")
    login(client, username)
    return admin


def test_requires_login(client):
    assert client.get(BASE).status_code == 401


def test_viewer_gets_403(client, make_user):
    make_user(role="viewer")
    login(client)
    assert client.get(BASE).status_code == 403


def test_list_hides_sensitive_fields(client, make_user):
    _as_admin(client, make_user)
    users = client.get(BASE).json()
    assert [u["username"] for u in users] == ["boss"]
    assert "password_hash" not in users[0] and "token_version" not in users[0]


def test_create_user(client, make_user):
    _as_admin(client, make_user)
    response = client.post(BASE, json={"username": "Carla", "password": TEST_PASSWORD, "role": "viewer"})
    assert response.status_code == 201
    assert response.json()["username"] == "carla"


def test_create_duplicate_409(client, make_user):
    _as_admin(client, make_user)
    make_user(username="carla")
    response = client.post(BASE, json={"username": "carla", "password": TEST_PASSWORD, "role": "viewer"})
    assert response.status_code == 409


def test_create_weak_password_422(client, make_user):
    _as_admin(client, make_user)
    response = client.post(BASE, json={"username": "carla", "password": "short", "role": "viewer"})
    assert response.status_code == 422


def test_patch_role_bumps_token_version(client, make_user):
    _as_admin(client, make_user)
    other = make_user(username="carla")
    response = client.patch(f"{BASE}/{other.id}", json={"role": "admin"})
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert other.token_version == 1


def test_cannot_deactivate_self(client, make_user):
    admin = _as_admin(client, make_user)
    assert client.patch(f"{BASE}/{admin.id}", json={"is_active": False}).status_code == 403


def test_cannot_demote_self(client, make_user):
    admin = _as_admin(client, make_user)
    assert client.patch(f"{BASE}/{admin.id}", json={"role": "viewer"}).status_code == 403


def test_cannot_reset_own_password(client, make_user):
    admin = _as_admin(client, make_user)
    response = client.post(f"{BASE}/{admin.id}/reset-password", json={"password": "a-new-long-password"})
    assert response.status_code == 403
    assert "reset-password" in response.json()["detail"]


def test_reset_other_password(client, make_user):
    _as_admin(client, make_user)
    other = make_user(username="carla")
    response = client.post(f"{BASE}/{other.id}/reset-password", json={"password": "a-new-long-password"})
    assert response.status_code == 204
    assert verify_password("a-new-long-password", other.password_hash)
    assert other.token_version == 1


def test_revoke_sessions(client, make_user):
    _as_admin(client, make_user)
    other = make_user(username="carla")
    assert client.post(f"{BASE}/{other.id}/revoke-sessions").status_code == 204
    assert other.token_version == 1


def test_unknown_user_404(client, make_user):
    _as_admin(client, make_user)
    assert client.get(f"{BASE}/999999").status_code == 404


def test_admin_crud_router_is_protected(client, make_user):
    assert client.get("/api/v1/admin/volumenes").status_code == 401
    make_user(username="vic", role="viewer")
    login(client, "vic")
    assert client.get("/api/v1/admin/volumenes").status_code == 403


def test_last_active_admin_cannot_be_demoted(make_user, test_db_session):
    from api.app.auth.user_admin import UserRuleError, update_user

    only_admin = make_user(username="boss", role="admin")
    actor = make_user(username="vic", role="viewer")  # simulates any other caller
    with pytest.raises(UserRuleError) as exc:
        update_user(test_db_session, actor, only_admin, {"role": "viewer"})
    assert exc.value.status_code == 409
