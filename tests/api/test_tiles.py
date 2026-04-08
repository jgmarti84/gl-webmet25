# tests/api/test_tiles.py
import httpx
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")

COGS_PREFIX = "/api/v1/cogs"
TILES_PREFIX = "/api/v1/tiles"


def _get_first_available_cog_id() -> int | None:
    """Return the ID of the first available COG, or None if no COGs exist."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(COGS_PREFIX, params={"page_size": 1})
        cogs = response.json().get("cogs", [])
    return cogs[0]["id"] if cogs else None


# ---------------------------------------------------------------------------
# GET /api/v1/tiles/{cog_id}/{z}/{x}/{y}.png
# ---------------------------------------------------------------------------

def test_tile_returns_200_for_valid_cog():
    """GET /tiles/{cog_id}/{z}/{x}/{y}.png must return HTTP 200 for a valid COG."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/5/0/0.png")
    assert response.status_code == 200


def test_tile_returns_png_content_type():
    """GET /tiles/{cog_id}/{z}/{x}/{y}.png must return image/png content type."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/5/0/0.png")
    assert response.status_code == 200
    assert "image/png" in response.headers["content-type"]


def test_tile_returns_non_empty_body():
    """GET /tiles/{cog_id}/{z}/{x}/{y}.png must return a non-empty body."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/5/0/0.png")
    assert response.status_code == 200
    assert len(response.content) > 0


def test_tile_returns_cache_control_header():
    """GET /tiles/{cog_id}/{z}/{x}/{y}.png must include Cache-Control header."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/5/0/0.png")
    assert response.status_code == 200
    assert "cache-control" in response.headers


def test_tile_returns_404_for_invalid_cog_id():
    """GET /tiles/{cog_id}/{z}/{x}/{y}.png must return 404 for a non-existent COG ID."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/999999999/5/0/0.png")
    assert response.status_code == 404


def test_tile_404_response_has_detail_field():
    """GET /tiles/{invalid_id}/{z}/{x}/{y}.png 404 response must include 'detail'."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/999999999/5/0/0.png")
    data = response.json()
    assert "detail" in data


def test_tile_colormap_override_returns_200():
    """GET /tiles/{cog_id}/{z}/{x}/{y}.png?colormap=viridis must return HTTP 200."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(
            f"{TILES_PREFIX}/{cog_id}/5/0/0.png",
            params={"colormap": "viridis"}
        )
    assert response.status_code == 200


def test_tile_vmin_vmax_override_returns_200():
    """GET /tiles/{cog_id}/{z}/{x}/{y}.png?vmin=0&vmax=80 must return HTTP 200."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(
            f"{TILES_PREFIX}/{cog_id}/5/0/0.png",
            params={"vmin": 0, "vmax": 80}
        )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/tiles/{cog_id}/metadata
# ---------------------------------------------------------------------------

def test_tile_metadata_returns_200():
    """GET /tiles/{cog_id}/metadata must return HTTP 200 for a valid COG."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/metadata")
    assert response.status_code == 200


def test_tile_metadata_returns_json():
    """GET /tiles/{cog_id}/metadata must return valid JSON with correct content type."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/metadata")
    assert "application/json" in response.headers["content-type"]


def test_tile_metadata_has_required_fields():
    """GET /tiles/{cog_id}/metadata must return all required contract fields."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/metadata")
    data = response.json()
    assert "cog_id" in data
    assert "data_type" in data
    assert "cmap" in data
    assert "vmin" in data
    assert "vmax" in data
    assert "available_colormaps" in data


def test_tile_metadata_available_colormaps_is_list():
    """GET /tiles/{cog_id}/metadata 'available_colormaps' must be a list."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/metadata")
    data = response.json()
    assert isinstance(data["available_colormaps"], list)


def test_tile_metadata_cog_id_matches_requested():
    """GET /tiles/{cog_id}/metadata must return the cog_id matching the request."""
    cog_id = _get_first_available_cog_id()
    assert cog_id is not None, "No COGs in database — cannot run test"
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/metadata")
    data = response.json()
    assert data["cog_id"] == cog_id


def test_tile_metadata_returns_404_for_invalid_cog_id():
    """GET /tiles/{cog_id}/metadata must return 404 for a non-existent COG ID."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/999999999/metadata")
    assert response.status_code == 404


def test_tile_metadata_404_has_detail_field():
    """GET /tiles/{invalid_id}/metadata 404 response must include 'detail'."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/999999999/metadata")
    data = response.json()
    assert "detail" in data


def test_tile_returns_cache_control_header():
    cog_id = _get_first_available_cog_id()
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/7/50/40.png")
    assert response.status_code == 200
    assert "Cache-Control" in response.headers
    assert "max-age" in response.headers["Cache-Control"]


def test_tile_returns_etag_header():
    cog_id = _get_first_available_cog_id()
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{TILES_PREFIX}/{cog_id}/7/50/40.png")
    assert "ETag" in response.headers


def test_tile_304_on_matching_etag():
    cog_id = _get_first_available_cog_id()
    with httpx.Client(base_url=API_BASE_URL) as client:
        r1 = client.get(f"{TILES_PREFIX}/{cog_id}/7/50/40.png")
        etag = r1.headers["ETag"]
        r2 = client.get(
            f"{TILES_PREFIX}/{cog_id}/7/50/40.png",
            headers={"If-None-Match": etag}
        )
    assert r2.status_code == 304


def test_different_colormap_produces_different_etag():
    cog_id = _get_first_available_cog_id()
    with httpx.Client(base_url=API_BASE_URL) as client:
        r1 = client.get(f"{TILES_PREFIX}/{cog_id}/7/50/40.png?colormap=viridis")
        r2 = client.get(f"{TILES_PREFIX}/{cog_id}/7/50/40.png?colormap=grc_th")
    assert r1.headers["ETag"] != r2.headers["ETag"]