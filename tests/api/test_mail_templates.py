# tests/api/test_mail_templates.py
"""Black-box contract tests for /api/v1/admin/mail-templates (spec F) against the isolated test stack.

They never save a text: without a session the endpoints refuse, with the bootstrap admin (the general admin) only
the read and the preview are used, and the bad bodies are refused before anything is written. The rules and the
mails themselves are tested in tests/auth/test_mail_templates.py.
"""

import os

import httpx
import pytest

from ._session import session_headers

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
URL = "/api/v1/admin/mail-templates"
KEYS = ["verify_email", "reset_password", "account_exists", "invitation"]
FOREIGN_ORIGIN = {"Origin": "https://evil.example"}
VALID = {
    "subject": "Asunto",
    "heading": "Título",
    "body": "Un párrafo.",
    "button": "Botón",
    "footer": "Pie",
    "fallback": "Alternativo",
}

ENDPOINTS = [
    ("get", URL, None),
    ("put", f"{URL}/verify_email", VALID),
    ("delete", f"{URL}/verify_email", None),
    ("post", f"{URL}/verify_email/preview", VALID),
]


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_mail_templates_without_session_return_401(method, path, body):
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.request(method, path, json=body).status_code == 401


def test_the_list_returns_the_four_mails_as_json():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(URL, headers=session_headers())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert sorted(item["key"] for item in response.json()) == sorted(KEYS)


def test_the_list_entries_have_the_contract_fields_and_types():
    with httpx.Client(base_url=API_BASE_URL) as client:
        items = client.get(URL, headers=session_headers()).json()
    for item in items:
        assert {"key", "title", "customized", "texts", "defaults", "placeholders"} <= set(item)
        assert isinstance(item["customized"], bool) and isinstance(item["title"], str)
        assert set(item["texts"]) == set(item["defaults"]) == set(VALID)
        assert all(isinstance(value, str) for value in item["texts"].values())
        assert all({"name", "example"} <= set(p) for p in item["placeholders"])


def test_the_preview_returns_the_subject_and_the_html_without_sending_anything():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{URL}/verify_email/preview", json=VALID, headers=session_headers())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["subject"] == "Asunto" and "Título" in body["html"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {**VALID, "subject": ""},
        {**VALID, "subject": "a\nb"},
        {**VALID, "body": "{no_existe}"},
        {**VALID, "key": "invitation"},
    ],
)
def test_bad_bodies_return_422_and_the_preview_writes_nothing(body):
    with httpx.Client(base_url=API_BASE_URL) as client:
        assert client.post(f"{URL}/verify_email/preview", json=body, headers=session_headers()).status_code == 422


def test_a_key_that_is_not_one_of_the_four_returns_422_json():
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.post(f"{URL}/nope/preview", json=VALID, headers=session_headers())
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("method,path,body", ENDPOINTS[1:])
def test_writes_from_a_foreign_origin_return_403(method, path, body):
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.request(method, path, json=body, headers={**session_headers(), **FOREIGN_ORIGIN})
    assert response.status_code == 403
