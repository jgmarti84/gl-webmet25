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


def test_create_user_with_a_mail_is_verified_and_normalized(client, make_user):
    _as_admin(client, make_user)
    response = client.post(
        BASE,
        json={"username": "carla", "password": TEST_PASSWORD, "role": "viewer", "email": "Carla@Ejemplo.com.ar"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "carla@ejemplo.com.ar"
    assert body["email_verified"] is True


def test_create_user_with_a_taken_mail_409(client, make_user):
    _as_admin(client, make_user)
    make_user(username="carla", email="carla@ejemplo.com.ar")
    response = client.post(
        BASE,
        json={"username": "otra", "password": TEST_PASSWORD, "role": "viewer", "email": "CARLA@ejemplo.com.ar"},
    )
    assert response.status_code == 409


def test_create_user_with_an_invalid_mail_422(client, make_user):
    _as_admin(client, make_user)
    response = client.post(
        BASE, json={"username": "otra", "password": TEST_PASSWORD, "role": "viewer", "email": "no-es-un-mail"}
    )
    assert response.status_code == 422


def test_patch_mail_normalizes_and_rejects_a_taken_one(client, make_user):
    _as_admin(client, make_user)
    make_user(username="carla", email="carla@ejemplo.com.ar")
    other = make_user(username="dario")
    ok = client.patch(f"{BASE}/{other.id}", json={"email": "Dario@Ejemplo.com.ar"})
    assert ok.status_code == 200 and ok.json()["email"] == "dario@ejemplo.com.ar"
    taken = client.patch(f"{BASE}/{other.id}", json={"email": "CARLA@ejemplo.com.ar"})
    assert taken.status_code == 409


def test_patch_can_clear_the_mail_and_keep_the_same_one(client, make_user):
    _as_admin(client, make_user)
    user = make_user(username="carla", email="carla@ejemplo.com.ar")
    assert client.patch(f"{BASE}/{user.id}", json={"email": "carla@ejemplo.com.ar"}).status_code == 200
    cleared = client.patch(f"{BASE}/{user.id}", json={"email": None})
    assert cleared.status_code == 200 and cleared.json()["email"] is None


def test_the_list_shows_whether_the_mail_is_verified(client, make_user):
    _as_admin(client, make_user)
    make_user(username="pend", email="pend@ejemplo.com.ar", email_verified=False)
    by_name = {u["username"]: u for u in client.get(BASE).json()}
    assert by_name["boss"]["email_verified"] is True
    assert by_name["pend"]["email_verified"] is False


# ---------------------------------------------------------------------------
# POST /admin/users/{id}/verify-email: the admin vouches for a mail that was never confirmed
# ---------------------------------------------------------------------------


def test_admin_verifies_a_pending_mail_and_the_person_can_log_in(client, make_user):
    _as_admin(client, make_user)
    pending = make_user(username="pend", email="pend@ejemplo.com.ar", email_verified=False)
    response = client.post(f"{BASE}/{pending.id}/verify-email")
    assert response.status_code == 200
    assert response.json()["email_verified"] is True
    assert pending.email_verified_at is not None
    # Until now this login was refused: the mail was not verified.
    assert login(client, "pend").status_code == 200


def test_verify_email_twice_keeps_the_first_date(client, make_user):
    _as_admin(client, make_user)
    pending = make_user(username="pend", email="pend@ejemplo.com.ar", email_verified=False)
    assert client.post(f"{BASE}/{pending.id}/verify-email").status_code == 200
    first = pending.email_verified_at
    assert client.post(f"{BASE}/{pending.id}/verify-email").status_code == 200
    assert pending.email_verified_at == first


def test_verify_email_of_an_account_without_mail_409(client, make_user):
    _as_admin(client, make_user)
    other = make_user(username="carla")
    response = client.post(f"{BASE}/{other.id}/verify-email")
    assert response.status_code == 409
    assert "mail" in response.json()["detail"]


def test_verify_email_unknown_user_404(client, make_user):
    _as_admin(client, make_user)
    assert client.post(f"{BASE}/999999/verify-email").status_code == 404


def test_verify_email_needs_an_admin(client, make_user):
    assert client.post(f"{BASE}/1/verify-email").status_code == 401
    make_user(username="vic", role="viewer")
    login(client, "vic")
    assert client.post(f"{BASE}/1/verify-email").status_code == 403
