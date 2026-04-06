# tests/api/test_radars.py
import httpx
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")

PREFIX = "/api/v1/radars"


# ---------------------------------------------------------------------------
# GET /api/v1/radars
# ---------------------------------------------------------------------------

def test_radars_returns_200():
    """GET /radars must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    assert response.status_code == 200


def test_radars_returns_json():
    """GET /radars must return valid JSON with correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    assert "application/json" in response.headers["content-type"]


def test_radars_response_has_required_fields():
    """GET /radars must return 'radars' list and 'count' integer."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    assert "radars" in data
    assert "count" in data
    assert isinstance(data["radars"], list)
    assert isinstance(data["count"], int)


def test_radars_count_matches_list_length():
    """GET /radars 'count' must equal the length of the 'radars' list."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    assert data["count"] == len(data["radars"])


def test_radars_items_have_required_fields():
    """Each radar in GET /radars must have all required contract fields."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    for radar in data["radars"]:
        assert "code" in radar
        assert "title" in radar
        assert "center_lat" in radar
        assert "center_long" in radar
        assert "is_active" in radar
        assert "extent" in radar


def test_radars_extent_has_required_fields():
    """Each radar's 'extent' must have lat_max, lat_min, lon_max, lon_min."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    for radar in data["radars"]:
        extent = radar["extent"]
        assert "lat_max" in extent
        assert "lat_min" in extent
        assert "lon_max" in extent
        assert "lon_min" in extent


def test_radars_active_only_true_returns_only_active():
    """GET /radars?active_only=true must return only active radars."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX, params={"active_only": "true"})
    data = response.json()
    for radar in data["radars"]:
        assert radar["is_active"] is True


def test_radars_active_only_false_returns_200():
    """GET /radars?active_only=false must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX, params={"active_only": "false"})
    assert response.status_code == 200


def test_radars_active_only_false_count_gte_active_only_true():
    """GET /radars?active_only=false must return >= radars than active_only=true."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        active = client.get(PREFIX, params={"active_only": "true"}).json()
        all_radars = client.get(PREFIX, params={"active_only": "false"}).json()
    assert all_radars["count"] >= active["count"]


# ---------------------------------------------------------------------------
# GET /api/v1/radars/{radar_code}
# ---------------------------------------------------------------------------

def test_radar_by_code_returns_200():
    """GET /radars/{code} must return HTTP 200 for a valid radar code."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        # Get a valid code from the list first
        radars = client.get(PREFIX).json()["radars"]
        assert len(radars) > 0, "No radars in database — cannot run test"
        code = radars[0]["code"]
        response = client.get(f"{PREFIX}/{code}")
    assert response.status_code == 200


def test_radar_by_code_returns_json():
    """GET /radars/{code} must return valid JSON with correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        radars = client.get(PREFIX).json()["radars"]
        assert len(radars) > 0, "No radars in database — cannot run test"
        code = radars[0]["code"]
        response = client.get(f"{PREFIX}/{code}")
    assert "application/json" in response.headers["content-type"]


def test_radar_by_code_response_has_required_fields():
    """GET /radars/{code} must return all required contract fields."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        radars = client.get(PREFIX).json()["radars"]
        assert len(radars) > 0, "No radars in database — cannot run test"
        code = radars[0]["code"]
        response = client.get(f"{PREFIX}/{code}")
    data = response.json()
    assert "code" in data
    assert "title" in data
    assert "center_lat" in data
    assert "center_long" in data
    assert "is_active" in data
    assert "extent" in data


def test_radar_by_code_returns_correct_radar():
    """GET /radars/{code} must return the radar matching the requested code."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        radars = client.get(PREFIX).json()["radars"]
        assert len(radars) > 0, "No radars in database — cannot run test"
        code = radars[0]["code"]
        response = client.get(f"{PREFIX}/{code}")
    data = response.json()
    assert data["code"] == code


def test_radar_by_invalid_code_returns_404():
    """GET /radars/{code} must return HTTP 404 for an unknown radar code."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/INVALID_RADAR_CODE_XYZ")
    assert response.status_code == 404


def test_radar_404_response_has_detail_field():
    """GET /radars/{invalid_code} 404 response must include a 'detail' field."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/INVALID_RADAR_CODE_XYZ")
    data = response.json()
    assert "detail" in data
