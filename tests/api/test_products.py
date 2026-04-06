# tests/api/test_products.py
import httpx
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")

PREFIX = "/api/v1/products"


# ---------------------------------------------------------------------------
# GET /api/v1/products
# ---------------------------------------------------------------------------

def test_products_returns_200():
    """GET /products must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    assert response.status_code == 200


def test_products_returns_json():
    """GET /products must return valid JSON with correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    assert "application/json" in response.headers["content-type"]


def test_products_response_has_required_fields():
    """GET /products must return 'products' list and 'count' integer."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    assert "products" in data
    assert "count" in data
    assert isinstance(data["products"], list)
    assert isinstance(data["count"], int)


def test_products_count_matches_list_length():
    """GET /products 'count' must equal the length of the 'products' list."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    assert data["count"] == len(data["products"])


def test_products_items_have_required_fields():
    """Each product in GET /products must have all required contract fields."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    for product in data["products"]:
        assert "id" in product
        assert "product_key" in product
        assert "product_title" in product
        assert "enabled" in product
        assert "min_value" in product
        assert "max_value" in product
        assert "unit" in product


def test_products_references_is_list():
    """Each product must include a 'references' list field."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX)
    data = response.json()
    for product in data["products"]:
        assert "references" in product
        assert isinstance(product["references"], list)


def test_products_enabled_only_true_returns_only_enabled():
    """GET /products?enabled_only=true must return only enabled products."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX, params={"enabled_only": "true"})
    data = response.json()
    for product in data["products"]:
        assert product["enabled"] is True


def test_products_enabled_only_false_returns_200():
    """GET /products?enabled_only=false must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(PREFIX, params={"enabled_only": "false"})
    assert response.status_code == 200


def test_products_enabled_only_false_count_gte_enabled_only_true():
    """GET /products?enabled_only=false must return >= products than enabled_only=true."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        enabled = client.get(PREFIX, params={"enabled_only": "true"}).json()
        all_products = client.get(PREFIX, params={"enabled_only": "false"}).json()
    assert all_products["count"] >= enabled["count"]


# ---------------------------------------------------------------------------
# GET /api/v1/products/{product_key}
# ---------------------------------------------------------------------------

def test_product_by_key_returns_200():
    """GET /products/{product_key} must return HTTP 200 for a valid key."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        products = client.get(PREFIX).json()["products"]
        assert len(products) > 0, "No products in database — cannot run test"
        key = products[0]["product_key"]
        response = client.get(f"{PREFIX}/{key}")
    assert response.status_code == 200


def test_product_by_key_returns_json():
    """GET /products/{product_key} must return valid JSON with correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        products = client.get(PREFIX).json()["products"]
        assert len(products) > 0, "No products in database — cannot run test"
        key = products[0]["product_key"]
        response = client.get(f"{PREFIX}/{key}")
    assert "application/json" in response.headers["content-type"]


def test_product_by_key_response_has_required_fields():
    """GET /products/{product_key} must return all required contract fields."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        products = client.get(PREFIX).json()["products"]
        assert len(products) > 0, "No products in database — cannot run test"
        key = products[0]["product_key"]
        response = client.get(f"{PREFIX}/{key}")
    data = response.json()
    assert "id" in data
    assert "product_key" in data
    assert "product_title" in data
    assert "enabled" in data
    assert "min_value" in data
    assert "max_value" in data
    assert "unit" in data
    assert "references" in data


def test_product_by_key_returns_correct_product():
    """GET /products/{product_key} must return the product matching the requested key."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        products = client.get(PREFIX).json()["products"]
        assert len(products) > 0, "No products in database — cannot run test"
        key = products[0]["product_key"]
        response = client.get(f"{PREFIX}/{key}")
    data = response.json()
    assert data["product_key"] == key


def test_product_by_invalid_key_returns_404():
    """GET /products/{product_key} must return HTTP 404 for an unknown product key."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/INVALID_PRODUCT_XYZ_99")
    assert response.status_code == 404


def test_product_404_response_has_detail_field():
    """GET /products/{invalid_key} 404 response must include a 'detail' field."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get(f"{PREFIX}/INVALID_PRODUCT_XYZ_99")
    data = response.json()
    assert "detail" in data
