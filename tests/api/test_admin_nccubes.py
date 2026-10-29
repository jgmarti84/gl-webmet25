# tests/api/test_admin_nccubes.py
"""Black-box contract tests for /api/v1/admin/nccubes (read only).

Protection (401 without a session, 200 and JSON for an admin) is covered with the other admin lists in
tests/api/test_admin.py; this file covers the response contract. Nothing here writes to the database.
"""

import os

import httpx
import pytest

from ._session import session_headers

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
PREFIX = "/api/v1/admin/nccubes"
UNKNOWN_ID = 999999999

# skipif with a reason (not a plain skip): an admin session needs the account db-init creates.
needs_admin = pytest.mark.skipif(
    not (os.getenv("ADMIN_USERNAME") and os.getenv("ADMIN_PASSWORD")),
    reason="ADMIN_USERNAME / ADMIN_PASSWORD not set",
)

ITEM_FIELDS = {
    "id",
    "radar_code",
    "observation_time",
    "file_path",
    "file_name",
    "file_size_bytes",
    "file_mtime",
    "status",
    "strategy",
    "vol_nr",
    "created_at",
    "updated_at",
}


def _get(path: str = "", **params):
    with httpx.Client(base_url=API_BASE_URL, headers=session_headers()) as client:
        return client.get(f"{PREFIX}{path}", params=params)


@needs_admin
def test_admin_nccubes_returns_200():
    """GET /admin/nccubes with an admin session returns 200."""
    assert _get(page_size=5).status_code == 200


@needs_admin
def test_admin_nccubes_response_has_required_fields():
    """The page carries pagination fields, and every item the full contract."""
    body = _get(page_size=5).json()
    assert {"page", "page_size", "total", "items"} <= body.keys()
    for item in body["items"]:
        assert ITEM_FIELDS <= item.keys()


@needs_admin
def test_admin_nccubes_returns_json():
    """GET /admin/nccubes answers with JSON."""
    assert "application/json" in _get(page_size=5).headers["content-type"]


@needs_admin
def test_admin_nccubes_unknown_id_returns_404():
    """An unknown cube id is a 404 with a detail, not a 500."""
    response = _get(f"/{UNKNOWN_ID}")
    assert response.status_code == 404
    assert "detail" in response.json()


@needs_admin
def test_admin_nccubes_invalid_page_returns_422():
    """page must be >= 1 and page_size <= 100."""
    assert _get(page=0).status_code == 422
    assert _get(page_size=101).status_code == 422


@needs_admin
def test_admin_nccubes_returns_list():
    """Field types match the contract; items are newest first and match the radar filter."""
    body = _get(page_size=20).json()
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int) and body["total"] >= len(body["items"])
    assert body["page"] == 1 and body["page_size"] == 20
    times = [item["observation_time"] for item in body["items"]]
    assert times == sorted(times, reverse=True)
    for item in body["items"]:
        assert isinstance(item["id"], int)
        assert isinstance(item["radar_code"], str)
        assert isinstance(item["file_name"], str)
        assert item["file_size_bytes"] is None or isinstance(
            item["file_size_bytes"], int
        )
    if body["items"]:
        radar = body["items"][0]["radar_code"]
        filtered = _get(radar_code=radar, page_size=20).json()
        assert filtered["items"] and all(
            i["radar_code"] == radar for i in filtered["items"]
        )
        one = _get(f"/{body['items'][0]['id']}").json()
        assert one["id"] == body["items"][0]["id"]
