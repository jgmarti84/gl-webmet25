# tests/api/test_cogs.py
import httpx
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")

PREFIX = "/api/v1/cogs"


# ---------------------------------------------------------------------------
# GET /api/v1/cogs
# ---------------------------------------------------------------------------

def test_cogs_returns_200():
    """GET /cogs must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    assert response.status_code == 200


def test_cogs_returns_json():
    """GET /cogs must return valid JSON with correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    assert "application/json" in response.headers["content-type"]


def test_cogs_response_has_required_fields():
    """GET /cogs must return all required pagination contract fields."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    assert "cogs" in data
    assert "count" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert isinstance(data["cogs"], list)


def test_cogs_count_matches_list_length():
    """GET /cogs 'count' must equal the length of the 'cogs' list."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    assert data["count"] == len(data["cogs"])


def test_cogs_items_have_required_fields():
    """Each COG in GET /cogs must have all required contract fields."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    for cog in data["cogs"]:
        assert "id" in cog
        assert "radar_code" in cog
        assert "observation_time" in cog
        assert "file_path" in cog
        assert "file_name" in cog
        assert "tile_url" in cog


def test_cogs_tile_url_contains_cog_id():
    """Each COG tile_url must embed the COG's own id."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    for cog in data["cogs"]:
        assert str(cog["id"]) in cog["tile_url"]


def test_cogs_default_page_is_1():
    """GET /cogs default response must have page == 1."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    assert data["page"] == 1


def test_cogs_default_page_size_is_50():
    """GET /cogs default response must have page_size == 50."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    assert data["page_size"] == 50


def test_cogs_filter_by_radar_code_returns_200():
    """GET /cogs?radar_code=X must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX, params={"radar_code": "RMA1"})
    assert response.status_code == 200


def test_cogs_filter_by_radar_code_returns_matching_only():
    """GET /cogs?radar_code=X must return only COGs for that radar."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        # Get a real radar code from the data
        all_cogs = client.get(PREFIX).json()["cogs"]
        if not all_cogs:
            return  # Skip: no COGs in database
        radar_code = all_cogs[0]["radar_code"]
        response = client.get(PREFIX, params={"radar_code": radar_code})
    data = response.json()
    for cog in data["cogs"]:
        assert cog["radar_code"] == radar_code


def test_cogs_filter_by_unknown_radar_code_returns_empty():
    """GET /cogs?radar_code=UNKNOWN must return an empty list (not an error)."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX, params={"radar_code": "UNKNOWN_RADAR_XYZ"})
    assert response.status_code == 200
    data = response.json()
    assert data["cogs"] == []
    assert data["count"] == 0


def test_cogs_pagination_page_size():
    """GET /cogs?page_size=2 must return at most 2 items."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX, params={"page_size": 2})
    data = response.json()
    assert len(data["cogs"]) <= 2
    assert data["page_size"] == 2


def test_cogs_pagination_page_2_returns_200():
    """GET /cogs?page=2 must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX, params={"page": 2})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/cogs/latest
# ---------------------------------------------------------------------------

def test_cogs_latest_returns_404_for_unknown_radar():
    """GET /cogs/latest must return 404 when no COG found for given radar+product."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(
            f"{PREFIX}/latest",
            params={"radar_code": "UNKNOWN_XYZ", "product_key": "UNKNOWN_XYZ"}
        )
    assert response.status_code == 404


def test_cogs_latest_404_has_detail_field():
    """GET /cogs/latest 404 response must include a 'detail' field."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(
            f"{PREFIX}/latest",
            params={"radar_code": "UNKNOWN_XYZ", "product_key": "UNKNOWN_XYZ"}
        )
    data = response.json()
    assert "detail" in data


# ---------------------------------------------------------------------------
# GET /api/v1/cogs/{cog_id}
# ---------------------------------------------------------------------------

def test_cog_by_id_returns_200():
    """GET /cogs/{cog_id} must return HTTP 200 for a valid ID."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        cogs = client.get(PREFIX).json()["cogs"]
        assert len(cogs) > 0, "No COGs in database — cannot run test"
        cog_id = cogs[0]["id"]
        response = client.get(f"{PREFIX}/{cog_id}")
    assert response.status_code == 200


def test_cog_by_id_returns_json():
    """GET /cogs/{cog_id} must return valid JSON with correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        cogs = client.get(PREFIX).json()["cogs"]
        assert len(cogs) > 0, "No COGs in database — cannot run test"
        cog_id = cogs[0]["id"]
        response = client.get(f"{PREFIX}/{cog_id}")
    assert "application/json" in response.headers["content-type"]


def test_cog_by_id_response_has_required_fields():
    """GET /cogs/{cog_id} must return all required contract fields."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        cogs = client.get(PREFIX).json()["cogs"]
        assert len(cogs) > 0, "No COGs in database — cannot run test"
        cog_id = cogs[0]["id"]
        response = client.get(f"{PREFIX}/{cog_id}")
    data = response.json()
    assert "id" in data
    assert "radar_code" in data
    assert "observation_time" in data
    assert "file_path" in data
    assert "tile_url" in data


def test_cog_by_id_returns_correct_id():
    """GET /cogs/{cog_id} must return the COG matching the requested ID."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        cogs = client.get(PREFIX).json()["cogs"]
        assert len(cogs) > 0, "No COGs in database — cannot run test"
        cog_id = cogs[0]["id"]
        response = client.get(f"{PREFIX}/{cog_id}")
    data = response.json()
    assert data["id"] == cog_id


def test_cog_by_invalid_id_returns_404():
    """GET /cogs/{cog_id} must return HTTP 404 for a non-existent ID."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/999999999")
    assert response.status_code == 404


def test_cog_404_response_has_detail_field():
    """GET /cogs/{invalid_id} 404 response must include a 'detail' field."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/999999999")
    data = response.json()
    assert "detail" in data
