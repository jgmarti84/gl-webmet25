# tests/api/test_users.py
"""Black-box contract tests for /api/v1/admin/users/* against the running API.

These tests never write to the database (apart from the admin's login session):

* The read endpoints (list, detail) are tested completely.
* The endpoints that write (create, edit, reset password, revoke sessions) are tested only on their error paths,
  and every error-path request uses an invalid payload or an unknown id, so that a regression answers 4xx
  instead of changing data. Their happy paths, and the rules about the admin's own account (cannot deactivate,
  demote or reset itself), run on the test database in tests/auth/test_users_router.py.
* The admin logs in once per run and the cookie is reused: expired sessions are never cleaned up, so one login
  per test would pile up rows in user_sessions.

The admin is the bootstrap account (ADMIN_USERNAME / ADMIN_PASSWORD). Responses without a body (204) have no content-type,
fields or data types to assert. The 403 answered to a logged-in viewer needs a second account and is covered
in tests/auth.
"""

import os
from typing import Any, Dict

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
PREFIX = "/api/v1/admin/users"
AUTH_PREFIX = "/api/v1/auth"
ADMIN_USER = os.getenv("ADMIN_USERNAME")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

# skipif with a reason (not a plain skip): these tests need the admin account db-init creates from ADMIN_USERNAME / ADMIN_PASSWORD.
needs_admin = pytest.mark.skipif(not (ADMIN_USER and ADMIN_PASS), reason="ADMIN_USERNAME / ADMIN_PASSWORD not set")

USER_FIELDS = {
    "id",
    "username",
    "full_name",
    "email",
    "email_verified",
    "role",
    "is_active",
    "password_is_bootstrap",
    "last_login_at",
    "created_at",
    "updated_at",
}
SENSITIVE_FIELDS = {"password_hash", "token_version", "failed_login_count", "locked_until"}
UNKNOWN_ID = 999999999
VALID_PASSWORD = "a-valid-long-password-123"
WEAK_PASSWORD = "short"
FOREIGN_ORIGIN = {"Origin": "https://evil.example"}
# Cookie names change with COOKIE_SECURE (prefixes), so the garbage cookie is sent under both names.
GARBAGE_ACCESS_COOKIE = {"Cookie": "webmet_access=garbage; __Host-webmet_access=garbage"}

_ADMIN: Dict[str, Any] = {}


def _admin_client() -> httpx.Client:
    """Client carrying the bootstrap admin's access cookie (the login happens once per test run)."""
    if not _ADMIN:
        with httpx.Client(base_url=API_BASE_URL) as client:
            response = client.post(f"{AUTH_PREFIX}/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
            assert response.status_code == 200, f"admin login failed: {response.status_code}"
            access = next(cookie for cookie in client.cookies.jar if cookie.name.endswith("webmet_access"))
            _ADMIN["cookie"] = f"{access.name}={access.value}"
            _ADMIN["me"] = response.json()
    return httpx.Client(base_url=API_BASE_URL, headers={"Cookie": _ADMIN["cookie"]})


def _own_id() -> int:
    """Id of the logged-in bootstrap admin."""
    with _admin_client():
        return _ADMIN["me"]["id"]


# ---------------------------------------------------------------------------
# GET /api/v1/admin/users
# ---------------------------------------------------------------------------


@needs_admin
def test_list_users_returns_200():
    """The user list must return HTTP 200 for an admin."""
    with _admin_client() as client:
        response = client.get(PREFIX)
    assert response.status_code == 200


@needs_admin
def test_list_users_returns_json():
    """The user list must return valid JSON with the correct content type."""
    with _admin_client() as client:
        response = client.get(PREFIX)
    assert "application/json" in response.headers["content-type"]


@needs_admin
def test_list_users_returns_a_list():
    """The user list must be a non-empty list."""
    with _admin_client() as client:
        data = client.get(PREFIX).json()
    assert isinstance(data, list)
    assert len(data) >= 1


@needs_admin
def test_list_users_items_have_required_fields():
    """Every user in the list must have all the contract fields."""
    with _admin_client() as client:
        data = client.get(PREFIX).json()
    for user in data:
        assert USER_FIELDS.issubset(user)


@needs_admin
def test_list_users_items_do_not_expose_sensitive_fields():
    """No user in the list may expose password hashes or lockout internals."""
    with _admin_client() as client:
        data = client.get(PREFIX).json()
    for user in data:
        assert SENSITIVE_FIELDS.isdisjoint(user)


@needs_admin
def test_list_users_item_field_types():
    """Every user field type must match the contract."""
    with _admin_client() as client:
        data = client.get(PREFIX).json()
    for user in data:
        assert isinstance(user["id"], int)
        assert isinstance(user["username"], str)
        assert user["full_name"] is None or isinstance(user["full_name"], str)
        assert user["email"] is None or isinstance(user["email"], str)
        assert user["role"] in ("admin", "viewer")
        assert isinstance(user["is_active"], bool)
        assert isinstance(user["password_is_bootstrap"], bool)
        assert user["last_login_at"] is None or isinstance(user["last_login_at"], str)
        assert user["created_at"] is None or isinstance(user["created_at"], str)


@needs_admin
def test_list_users_includes_the_bootstrap_admin():
    """The account the tests log in with must be in the list, as an active admin."""
    with _admin_client() as client:
        data = client.get(PREFIX).json()
    admins = [user for user in data if user["username"] == ADMIN_USER.lower()]
    assert len(admins) == 1
    assert admins[0]["role"] == "admin"
    assert admins[0]["is_active"] is True


@needs_admin
def test_list_users_is_sorted_by_username():
    """The list must come sorted by username."""
    with _admin_client() as client:
        usernames = [user["username"] for user in client.get(PREFIX).json()]
    assert usernames == sorted(usernames)


def test_list_users_without_session_returns_401():
    """The user list without a session must return 401."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    assert response.status_code == 401
    assert "detail" in response.json()


def test_list_users_with_garbage_cookie_returns_401():
    """The user list with a forged access cookie must return 401."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX, headers=GARBAGE_ACCESS_COOKIE)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/admin/users/{id}
# ---------------------------------------------------------------------------


@needs_admin
def test_get_user_returns_200():
    """The detail of an existing user must return HTTP 200."""
    with _admin_client() as client:
        response = client.get(f"{PREFIX}/{_own_id()}")
    assert response.status_code == 200


@needs_admin
def test_get_user_returns_json():
    """The user detail must return valid JSON with the correct content type."""
    with _admin_client() as client:
        response = client.get(f"{PREFIX}/{_own_id()}")
    assert "application/json" in response.headers["content-type"]


@needs_admin
def test_get_user_response_has_required_fields():
    """The user detail must have all the contract fields and none of the sensitive ones."""
    with _admin_client() as client:
        data = client.get(f"{PREFIX}/{_own_id()}").json()
    assert USER_FIELDS.issubset(data)
    assert SENSITIVE_FIELDS.isdisjoint(data)


@needs_admin
def test_get_user_response_field_types():
    """The user detail field types must match the contract."""
    with _admin_client() as client:
        data = client.get(f"{PREFIX}/{_own_id()}").json()
    assert isinstance(data["id"], int)
    assert isinstance(data["username"], str)
    assert data["role"] in ("admin", "viewer")
    assert isinstance(data["is_active"], bool)
    assert isinstance(data["password_is_bootstrap"], bool)


@needs_admin
def test_get_user_matches_the_list_entry():
    """The detail of a user must be the same record the list shows."""
    with _admin_client() as client:
        detail = client.get(f"{PREFIX}/{_own_id()}").json()
        listed = [user for user in client.get(PREFIX).json() if user["id"] == detail["id"]]
    assert listed == [detail]


@needs_admin
def test_get_user_unknown_id_returns_404():
    """An unknown user id must return 404 with a JSON detail."""
    with _admin_client() as client:
        response = client.get(f"{PREFIX}/{UNKNOWN_ID}")
    assert response.status_code == 404
    assert "detail" in response.json()


@needs_admin
def test_get_user_non_integer_id_returns_422():
    """A non-numeric user id must return 422."""
    with _admin_client() as client:
        response = client.get(f"{PREFIX}/not-a-number")
    assert response.status_code == 422


def test_get_user_without_session_returns_401():
    """The user detail without a session must return 401."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/1")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/admin/users   (error paths only: a valid request would create a user)
# ---------------------------------------------------------------------------


def test_create_user_without_session_returns_401():
    """Creating a user without a session must return 401 (the payload is invalid on purpose)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(PREFIX, json={"username": "contract-test", "password": WEAK_PASSWORD, "role": "viewer"})
    assert response.status_code == 401


@needs_admin
def test_create_user_foreign_origin_returns_403():
    """Creating a user from a foreign Origin must be rejected (the payload is invalid on purpose)."""
    with _admin_client() as client:
        response = client.post(
            PREFIX,
            json={"username": "contract-test", "password": WEAK_PASSWORD, "role": "viewer"},
            headers=FOREIGN_ORIGIN,
        )
    assert response.status_code == 403


@needs_admin
def test_create_user_missing_fields_returns_422():
    """A body without the required fields must return 422."""
    with _admin_client() as client:
        response = client.post(PREFIX, json={})
    assert response.status_code == 422


@needs_admin
def test_create_user_weak_password_returns_422():
    """A password shorter than 12 characters must return 422."""
    with _admin_client() as client:
        response = client.post(PREFIX, json={"username": "contract-test", "password": WEAK_PASSWORD, "role": "viewer"})
    assert response.status_code == 422


@needs_admin
def test_create_user_invalid_role_returns_422():
    """A role other than admin or viewer must return 422."""
    with _admin_client() as client:
        response = client.post(PREFIX, json={"username": "contract-test", "password": VALID_PASSWORD, "role": "root"})
    assert response.status_code == 422


@needs_admin
def test_create_user_too_short_username_returns_422():
    """A username under 3 characters must return 422."""
    with _admin_client() as client:
        response = client.post(PREFIX, json={"username": "ab", "password": WEAK_PASSWORD, "role": "viewer"})
    assert response.status_code == 422


@needs_admin
def test_create_user_invalid_username_characters_returns_422():
    """A username with spaces must return 422 (the weak password stops it from ever being created)."""
    with _admin_client() as client:
        response = client.post(PREFIX, json={"username": "bad name", "password": WEAK_PASSWORD, "role": "viewer"})
    assert response.status_code == 422


@needs_admin
def test_create_user_duplicate_username_returns_409():
    """Creating a user whose username already exists must return 409 and create nothing."""
    with _admin_client() as client:
        response = client.post(PREFIX, json={"username": ADMIN_USER, "password": VALID_PASSWORD, "role": "viewer"})
    assert response.status_code == 409
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/users/{id}
# ---------------------------------------------------------------------------


@needs_admin
def test_patch_user_with_empty_body_returns_200():
    """An edit with no changes must return HTTP 200."""
    with _admin_client() as client:
        response = client.patch(f"{PREFIX}/{_own_id()}", json={})
    assert response.status_code == 200


@needs_admin
def test_patch_user_with_empty_body_returns_json_with_required_fields():
    """An edit must return the user as JSON with all the contract fields."""
    with _admin_client() as client:
        response = client.patch(f"{PREFIX}/{_own_id()}", json={})
    assert "application/json" in response.headers["content-type"]
    assert USER_FIELDS.issubset(response.json())
    assert SENSITIVE_FIELDS.isdisjoint(response.json())


@needs_admin
def test_patch_user_with_empty_body_changes_nothing():
    """An edit with no changes must leave the user exactly as it was."""
    with _admin_client() as client:
        before = client.get(f"{PREFIX}/{_own_id()}").json()
        patched = client.patch(f"{PREFIX}/{_own_id()}", json={}).json()
        after = client.get(f"{PREFIX}/{_own_id()}").json()
    assert patched == before
    assert after == before


@needs_admin
def test_patch_user_invalid_role_returns_422():
    """A role other than admin or viewer must return 422."""
    with _admin_client() as client:
        response = client.patch(f"{PREFIX}/{_own_id()}", json={"role": "root"})
    assert response.status_code == 422


@needs_admin
def test_patch_user_unknown_id_returns_404():
    """Editing an unknown user must return 404."""
    with _admin_client() as client:
        response = client.patch(f"{PREFIX}/{UNKNOWN_ID}", json={"full_name": "Nobody"})
    assert response.status_code == 404
    assert "detail" in response.json()


@needs_admin
def test_patch_user_foreign_origin_returns_403():
    """Editing a user from a foreign Origin must be rejected (the id is unknown on purpose)."""
    with _admin_client() as client:
        response = client.patch(f"{PREFIX}/{UNKNOWN_ID}", json={"full_name": "Nobody"}, headers=FOREIGN_ORIGIN)
    assert response.status_code == 403


def test_patch_user_without_session_returns_401():
    """Editing a user without a session must return 401 (the id is unknown on purpose)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.patch(f"{PREFIX}/{UNKNOWN_ID}", json={"full_name": "Nobody"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/admin/users/{id}/reset-password   (204: error paths only)
# ---------------------------------------------------------------------------


@needs_admin
def test_reset_password_for_own_account_returns_403():
    """An admin cannot reset their own password from the API (the password is weak on purpose)."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{_own_id()}/reset-password", json={"password": WEAK_PASSWORD})
    assert response.status_code == 403


@needs_admin
def test_reset_password_for_own_account_points_to_the_server_command():
    """The 403 must tell the admin to use the server command."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{_own_id()}/reset-password", json={"password": WEAK_PASSWORD})
    assert "reset-password" in response.json()["detail"]


@needs_admin
def test_reset_password_unknown_id_returns_404():
    """Resetting the password of an unknown user must return 404."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/reset-password", json={"password": WEAK_PASSWORD})
    assert response.status_code == 404


@needs_admin
def test_reset_password_missing_body_returns_422():
    """A reset without a password must return 422."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/reset-password", json={})
    assert response.status_code == 422


@needs_admin
def test_reset_password_empty_password_returns_422():
    """An empty password must return 422."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/reset-password", json={"password": ""})
    assert response.status_code == 422


@needs_admin
def test_reset_password_too_long_password_returns_422():
    """A password over 128 characters must return 422."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/reset-password", json={"password": "a" * 129})
    assert response.status_code == 422


@needs_admin
def test_reset_password_foreign_origin_returns_403():
    """A reset from a foreign Origin must be rejected (the id is unknown on purpose)."""
    with _admin_client() as client:
        response = client.post(
            f"{PREFIX}/{UNKNOWN_ID}/reset-password", json={"password": WEAK_PASSWORD}, headers=FOREIGN_ORIGIN
        )
    assert response.status_code == 403


def test_reset_password_without_session_returns_401():
    """A reset without a session must return 401 (the id is unknown on purpose)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/reset-password", json={"password": WEAK_PASSWORD})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/admin/users/{id}/revoke-sessions   (204: error paths only)
# ---------------------------------------------------------------------------


@needs_admin
def test_revoke_sessions_unknown_id_returns_404():
    """Revoking the sessions of an unknown user must return 404."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/revoke-sessions")
    assert response.status_code == 404
    assert "detail" in response.json()


@needs_admin
def test_revoke_sessions_foreign_origin_returns_403():
    """Revoking sessions from a foreign Origin must be rejected (the id is unknown on purpose)."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/revoke-sessions", headers=FOREIGN_ORIGIN)
    assert response.status_code == 403


def test_revoke_sessions_without_session_returns_401():
    """Revoking sessions without a session must return 401 (the id is unknown on purpose)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/revoke-sessions")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/admin/users/{id}/verify-email   (200: error paths only)
# ---------------------------------------------------------------------------


@needs_admin
def test_verify_email_unknown_id_returns_404():
    """Verifying the mail of an unknown user must return 404."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/verify-email")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "detail" in response.json()


@needs_admin
def test_verify_email_foreign_origin_returns_403():
    """Verifying a mail from a foreign Origin must be rejected (the id is unknown on purpose)."""
    with _admin_client() as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/verify-email", headers=FOREIGN_ORIGIN)
    assert response.status_code == 403


def test_verify_email_without_session_returns_401():
    """Verifying a mail without a session must return 401 (the id is unknown on purpose)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PREFIX}/{UNKNOWN_ID}/verify-email")
    assert response.status_code == 401
