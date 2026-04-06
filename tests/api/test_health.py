# tests/api/test_health.py
import pytest
import httpx
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")


def test_health_returns_200():
    """Health endpoint must return HTTP 200."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_status_ok():
    """Health endpoint must return status ok."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"


def test_health_database_is_connected():
    """Health endpoint must confirm database is connected."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get("/health")
    data = response.json()
    assert data["database"] is True


def test_health_response_has_required_fields():
    """Health endpoint must return all required contract fields."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "timestamp" in data


def test_health_returns_json():
    """Health endpoint must return valid JSON with correct content type."""
    with httpx.Client(base_url=API_BASE_URL) as client:
        response = client.get("/health")
    assert "application/json" in response.headers["content-type"]