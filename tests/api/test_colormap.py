# tests/api/test_colormap.py
import httpx
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")

COLORMAP_PREFIX = "/api/v1/colormap"
PRODUCTS_PREFIX = "/api/v1/products"


# ---------------------------------------------------------------------------
# GET /api/v1/colormap/options
# ---------------------------------------------------------------------------

def test_colormap_options_returns_200():
    """GET /colormap/options must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/options")
    assert response.status_code == 200


def test_colormap_options_returns_json():
    """GET /colormap/options must return valid JSON with correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/options")
    assert "application/json" in response.headers["content-type"]


def test_colormap_options_returns_dict_of_lists():
    """GET /colormap/options must return a dict mapping product keys to lists."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/options")
    data = response.json()
    assert isinstance(data, dict)
    for key, value in data.items():
        assert isinstance(key, str)
        assert isinstance(value, list)


# ---------------------------------------------------------------------------
# GET /api/v1/colormap/defaults
# ---------------------------------------------------------------------------

def test_colormap_defaults_returns_200():
    """GET /colormap/defaults must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/defaults")
    assert response.status_code == 200


def test_colormap_defaults_returns_json():
    """GET /colormap/defaults must return valid JSON with correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/defaults")
    assert "application/json" in response.headers["content-type"]


def test_colormap_defaults_returns_dict_of_strings():
    """GET /colormap/defaults must return a dict mapping product keys to colormap names."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/defaults")
    data = response.json()
    assert isinstance(data, dict)
    for key, value in data.items():
        assert isinstance(key, str)
        assert isinstance(value, str)


# ---------------------------------------------------------------------------
# GET /api/v1/colormap/colors/{cmap_name}
# ---------------------------------------------------------------------------

def test_colormap_colors_returns_200_for_valid_cmap():
    """GET /colormap/colors/{cmap_name} must return HTTP 200 for a known colormap."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/colors/viridis")
    assert response.status_code == 200


def test_colormap_colors_returns_json():
    """GET /colormap/colors/{cmap_name} must return valid JSON."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/colors/viridis")
    assert "application/json" in response.headers["content-type"]


def test_colormap_colors_response_has_required_fields():
    """GET /colormap/colors/{cmap_name} must return 'colors', 'steps', 'colormap'."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/colors/viridis")
    data = response.json()
    assert "colors" in data
    assert "steps" in data
    assert "colormap" in data


def test_colormap_colors_returns_list_of_hex_colors():
    """GET /colormap/colors/{cmap_name} must return a list of hex color strings."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/colors/viridis")
    data = response.json()
    assert isinstance(data["colors"], list)
    assert len(data["colors"]) > 0
    for color in data["colors"]:
        assert isinstance(color, str)
        assert color.startswith("#")


def test_colormap_colors_default_steps_is_256():
    """GET /colormap/colors/{cmap_name} default must return 256 steps."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/colors/viridis")
    data = response.json()
    assert data["steps"] == 256
    assert len(data["colors"]) == 256


def test_colormap_colors_custom_steps():
    """GET /colormap/colors/{cmap_name}?steps=10 must return exactly 10 colors."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/colors/viridis", params={"steps": 10})
    data = response.json()
    assert data["steps"] == 10
    assert len(data["colors"]) == 10


def test_colormap_colors_returns_400_for_invalid_cmap():
    """GET /colormap/colors/{cmap_name} must return HTTP 400 for an unknown colormap."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/colors/INVALID_CMAP_XYZ_99")
    assert response.status_code == 400


def test_colormap_colors_400_has_detail_field():
    """GET /colormap/colors/{invalid_cmap} 400 response must include 'detail'."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/colors/INVALID_CMAP_XYZ_99")
    data = response.json()
    assert "detail" in data


# ---------------------------------------------------------------------------
# GET /api/v1/colormap/info/{product_key}
# ---------------------------------------------------------------------------

def test_colormap_info_returns_200_for_valid_product():
    """GET /colormap/info/{product_key} must return HTTP 200 for a known product."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/info/DBZH")
    assert response.status_code == 200


def test_colormap_info_returns_json():
    """GET /colormap/info/{product_key} must return valid JSON."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/info/DBZH")
    assert "application/json" in response.headers["content-type"]


def test_colormap_info_has_required_fields():
    """GET /colormap/info/{product_key} must return all required contract fields."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/info/DBZH")
    data = response.json()
    assert "product_key" in data
    assert "colormap" in data
    assert "vmin" in data
    assert "vmax" in data
    assert "colors" in data
    assert "available_colormaps" in data


def test_colormap_info_colors_is_list_of_hex():
    """GET /colormap/info/{product_key} must return 'colors' as a list of hex strings."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/info/DBZH")
    data = response.json()
    assert isinstance(data["colors"], list)
    assert len(data["colors"]) > 0
    for color in data["colors"]:
        assert color.startswith("#")


def test_colormap_info_vmin_less_than_vmax():
    """GET /colormap/info/{product_key} vmin must be less than vmax."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{COLORMAP_PREFIX}/info/DBZH")
    data = response.json()
    assert data["vmin"] < data["vmax"]


def test_colormap_info_colormap_override():
    """GET /colormap/info/{product_key}?colormap=viridis must accept colormap override."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(
            f"{COLORMAP_PREFIX}/info/DBZH",
            params={"colormap": "viridis"}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["colormap"] == "viridis"


# ---------------------------------------------------------------------------
# GET /api/v1/products/{product_key}/colormap  (deprecated endpoint)
# ---------------------------------------------------------------------------

def test_deprecated_product_colormap_returns_200():
    """GET /products/{product_key}/colormap must return HTTP 200 for a valid key."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        products = client.get(f"{PRODUCTS_PREFIX}").json()["products"]
        if not products:
            return  # Skip: no products in database
        # Find a product that has references (needed for colormap)
        key = products[0]["product_key"]
        response = client.get(f"{PRODUCTS_PREFIX}/{key}/colormap")
    assert response.status_code == 200


def test_deprecated_product_colormap_returns_json():
    """GET /products/{product_key}/colormap must return valid JSON."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        products = client.get(f"{PRODUCTS_PREFIX}").json()["products"]
        if not products:
            return  # Skip: no products in database
        key = products[0]["product_key"]
        response = client.get(f"{PRODUCTS_PREFIX}/{key}/colormap")
    assert "application/json" in response.headers["content-type"]


def test_deprecated_product_colormap_has_required_fields():
    """GET /products/{product_key}/colormap must return 'product_key', 'entries', 'min_value', 'max_value', 'unit'."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        products = client.get(f"{PRODUCTS_PREFIX}").json()["products"]
        if not products:
            return  # Skip: no products in database
        key = products[0]["product_key"]
        response = client.get(f"{PRODUCTS_PREFIX}/{key}/colormap")
    data = response.json()
    assert "product_key" in data
    assert "entries" in data
    assert "min_value" in data
    assert "max_value" in data
    assert "unit" in data


def test_deprecated_product_colormap_returns_404_for_invalid_key():
    """GET /products/{product_key}/colormap must return 404 for an unknown key."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PRODUCTS_PREFIX}/INVALID_PRODUCT_XYZ_99/colormap")
    assert response.status_code == 404


def test_deprecated_product_colormap_404_has_detail_field():
    """GET /products/{invalid_key}/colormap 404 response must include 'detail'."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PRODUCTS_PREFIX}/INVALID_PRODUCT_XYZ_99/colormap")
    data = response.json()
    assert "detail" in data
