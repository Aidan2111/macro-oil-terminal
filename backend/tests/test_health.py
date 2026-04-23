"""Health endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import create_app


def test_root_health_returns_ok():
    """GET /health returns {"ok": True} for App Service probes."""
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_api_health_returns_ok():
    """GET /api/health returns the same payload, served through the proxy."""
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
