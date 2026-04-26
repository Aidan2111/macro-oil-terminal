"""Tests for `backend.security` — origin allowlist + persistent rate limit.

Wave 4 hardening, review #14 findings S-3 (origin) and S-4 (rate limit).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


SWA_ORIGIN = "https://delightful-pebble-00d8eb30f.7.azurestaticapps.net"
EVIL_ORIGIN = "https://evil.example.com"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient + isolated rate-limit state path. Resets the on-disk
    state file before and after each test so tests don't interfere."""
    monkeypatch.setenv("ALPACA_PAPER", "true")
    monkeypatch.setenv("RATE_LIMIT_STATE_DIR", str(tmp_path))
    from backend.main import app
    from backend import security

    security._reset_state_for_test()
    yield TestClient(app)
    security._reset_state_for_test()


def _payload() -> dict:
    return {
        "symbol": "AAPL",
        "qty": 1,
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
    }


# ---------------------------------------------------------------------------
# S-3 — origin allowlist
# ---------------------------------------------------------------------------


def test_execute_blocks_disallowed_origin(client):
    resp = client.post(
        "/api/positions/execute",
        json=_payload(),
        headers={"Origin": EVIL_ORIGIN},
    )
    assert resp.status_code == 403, resp.text
    assert "not allowed" in resp.json()["detail"].lower()


def test_execute_no_origin_header_passes_origin_gate(client):
    resp = client.post("/api/positions/execute", json=_payload())
    if resp.status_code == 403:
        assert "not allowed" not in resp.json().get("detail", "").lower()


def test_execute_allowed_swa_origin_passes_origin_gate(client):
    resp = client.post(
        "/api/positions/execute",
        json=_payload(),
        headers={"Origin": SWA_ORIGIN},
    )
    if resp.status_code == 403:
        assert "not allowed" not in resp.json().get("detail", "").lower()


# ---------------------------------------------------------------------------
# S-4 — persistent rate limit (inner floor + outer ceiling)
# ---------------------------------------------------------------------------


def test_execute_inner_floor_kicks_in_on_back_to_back_calls(client):
    """Two rapid calls -> second hits the 1-req-per-2s inner floor (429)."""
    r1 = client.post("/api/positions/execute", json=_payload())
    r2 = client.post("/api/positions/execute", json=_payload())
    assert r2.status_code == 429, (r1.status_code, r2.status_code, r2.text)
    assert "Retry-After" in r2.headers
    assert int(r2.headers["Retry-After"]) >= 1


def test_execute_outer_ceiling_kicks_in_after_31_rapid_calls(client, monkeypatch):
    """31 rapid calls with the inner floor neutralised -> 31st is 429."""
    from backend import security

    monkeypatch.setattr(security, "EXECUTE_MIN_INTERVAL_S", 0.0)
    statuses = []
    for _ in range(31):
        r = client.post("/api/positions/execute", json=_payload())
        statuses.append(r.status_code)
    burst_hit = any(s == 429 for s in statuses[-3:])
    assert burst_hit, f"expected a 429 in the last few calls; got {statuses}"


def test_execute_state_persists_to_disk(client, tmp_path):
    """The bucket file should exist on disk after one call so a container
    restart can re-load it (which is the point of S-4)."""
    client.post("/api/positions/execute", json=_payload())
    state_file = tmp_path / "rate-limit-execute.json"
    assert state_file.exists(), f"expected {state_file} on disk"
    import json

    state = json.loads(state_file.read_text())
    assert "last_call" in state
    assert isinstance(state.get("timestamps"), list) and state["timestamps"]
