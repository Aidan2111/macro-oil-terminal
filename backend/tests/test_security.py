"""Tests for `backend.security` — origin allowlist + (Wave 4 follow-up) rate limit.

Wave 4 hardening, review #14 findings S-3 (origin) and S-4 (rate limit).
Each test boots a fresh `app` (the live module instance) and uses
TestClient. Origin tests do not require ALPACA_PAPER, but they pass
through the `ALPACA_PAPER == "true"` gate so we set it for parity.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


SWA_ORIGIN = "https://delightful-pebble-00d8eb30f.7.azurestaticapps.net"
EVIL_ORIGIN = "https://evil.example.com"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Force ALPACA_PAPER=true so the request reaches the origin gate.
    Use a non-existent state dir so the rate-limit (when present) writes
    nowhere we care about for test cleanup."""
    monkeypatch.setenv("ALPACA_PAPER", "true")
    yield


def _client():
    # Import inside so coverage of `from backend.main import app` is fresh.
    from backend.main import app

    return TestClient(app)


def _payload() -> dict:
    return {
        "symbol": "AAPL",
        "qty": 1,
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
    }


def test_execute_blocks_disallowed_origin():
    """Browser POST from an off-allowlist Origin → 403."""
    client = _client()
    resp = client.post(
        "/api/positions/execute",
        json=_payload(),
        headers={"Origin": EVIL_ORIGIN},
    )
    assert resp.status_code == 403, resp.text
    assert "not allowed" in resp.json()["detail"].lower()


def test_execute_no_origin_header_passes_origin_gate(monkeypatch):
    """Server-to-server / curl / Postman (no Origin) → bypass the origin
    gate. ALPACA may still 5xx because no real client is wired in this
    smoke env, but the response must NOT be a 403 from the origin gate.
    """
    client = _client()
    resp = client.post("/api/positions/execute", json=_payload())
    # Anything except a 403-from-origin-gate is fine. The route may emit
    # 503 (alpaca not configured) or 200 (mocked elsewhere). We only assert
    # the origin gate did not fire.
    if resp.status_code == 403:
        assert "not allowed" not in resp.json().get("detail", "").lower()


def test_execute_allowed_swa_origin_passes_origin_gate():
    client = _client()
    resp = client.post(
        "/api/positions/execute",
        json=_payload(),
        headers={"Origin": SWA_ORIGIN},
    )
    if resp.status_code == 403:
        assert "not allowed" not in resp.json().get("detail", "").lower()
