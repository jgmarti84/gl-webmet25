# tests/api/test_invitations.py
"""Black-box contract tests for the invitation endpoints (spec E) against the isolated test stack.

They never create data: without a session or with the bootstrap admin (who is not a company admin) the endpoints
refuse, and the public ones are only asked about tokens that do not exist. The happy paths and the rules run in
tests/auth/test_invitations.py.
"""

import os

import httpx
import pytest

from ._session import session_headers

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
ADMIN = "/api/v1/admin/invitations"
ORG = "/api/v1/org/invitations"
PUBLIC = "/api/v1/invitations"
GHOST = "00000000-0000-0000-0000-000000000000"
FOREIGN_ORIGIN = {"Origin": "https://evil.example"}
UNKNOWN_TOKEN = "A" * 43

ADMIN_ENDPOINTS = [
    ("get", ADMIN, None),
    ("post", ADMIN, {"email": "nadie@ejemplo.com.ar", "organization_id": 999999999, "role": "org_admin"}),
    ("post", f"{ADMIN}/{GHOST}/resend", None),
    ("post", f"{ADMIN}/{GHOST}/cancel", None),
]
ORG_ENDPOINTS = [
    ("get", ORG, None),
    ("post", ORG, {"email": "nadie@ejemplo.com.ar"}),
    ("post", f"{ORG}/{GHOST}/resend", None),
    ("post", f"{ORG}/{GHOST}/cancel", None),
]


@pytest.mark.parametrize("method,path,body", ADMIN_ENDPOINTS + ORG_ENDPOINTS)
def test_invitations_without_session_return_401(method, path, body):
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.request(method, path, json=body).status_code == 401


@pytest.mark.parametrize("method,path,body", ORG_ENDPOINTS)
def test_the_company_endpoints_refuse_the_general_admin_with_403_json(method, path, body):
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.request(method, path, json=body, headers=session_headers())
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")


def test_creating_for_an_unknown_company_returns_404_json():
    body = {"email": "nadie@ejemplo.com.ar", "organization_id": 999999999, "role": "org_admin"}
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(ADMIN, json=body, headers=session_headers())
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_creating_with_an_invalid_body_returns_422():
    body = {"email": "no-es-un-mail", "organization_id": 1, "role": "admin"}
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.post(ADMIN, json=body, headers=session_headers()).status_code == 422


def test_cancel_and_resend_of_an_unknown_invitation_return_404():
    with httpx.Client(base_url=API_BASE_URL) as client:
        for action in ("cancel", "resend"):
            response = client.post(f"{ADMIN}/{GHOST}/{action}", headers=session_headers())
            assert response.status_code == 404
            assert response.headers["content-type"].startswith("application/json")


def test_the_list_returns_a_json_list():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(ADMIN, headers=session_headers())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert isinstance(response.json(), list)


def test_the_list_entries_have_the_contract_fields_and_never_the_token():
    with httpx.Client(base_url=API_BASE_URL) as client:
        items = client.get(ADMIN, headers=session_headers()).json()
    for item in items:
        assert {"id", "email", "organization_id", "organization_name", "role", "created_at", "expires_at"} <= set(item)
        assert isinstance(item["email"], str) and item["role"] in ("org_admin", "viewer")
        assert "token" not in item and "token_hash" not in item


# --- the public endpoints (no session) -----------------------------------------------------------------------


@pytest.mark.parametrize("token", [UNKNOWN_TOKEN, "corto", "", "' OR 1=1 --"])
def test_details_of_an_unusable_link_return_the_generic_404(token):
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PUBLIC}/details", json={"token": token})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert isinstance(response.json()["detail"], str)


def test_accept_with_an_unusable_link_returns_404():
    body = {"token": UNKNOWN_TOKEN, "username": "nadie", "password": "correct-horse-battery", "accept_terms": True}
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.post(f"{PUBLIC}/accept", json=body).status_code == 404


def test_accept_without_the_required_fields_returns_422():
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.post(f"{PUBLIC}/accept", json={"token": UNKNOWN_TOKEN}).status_code == 422
        assert client.post(f"{PUBLIC}/details", json={}).status_code == 422


@pytest.mark.parametrize("path", ["/details", "/accept", "/accept-google", "/accept-existing"])
def test_public_posts_from_a_foreign_origin_return_403(path):
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.post(f"{PUBLIC}{path}", json={}, headers=FOREIGN_ORIGIN).status_code == 403


# --- accept-existing: joining with an account that already exists ---------------------------------------
# It needs a session of the account of the invited mail. Here only its error paths: nothing is accepted or changed.


def test_accept_existing_without_a_session_returns_401_json():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PUBLIC}/accept-existing", json={"token": UNKNOWN_TOKEN})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")


def test_accept_existing_with_a_session_but_an_unusable_link_returns_404():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{PUBLIC}/accept-existing", json={"token": UNKNOWN_TOKEN}, headers=session_headers())
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


def test_accept_existing_with_an_invalid_body_returns_422():
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.post(f"{PUBLIC}/accept-existing", json={}, headers=session_headers()).status_code == 422
