"""Tests for the `/api/fleet/*` routes + the fleet service fan-out.

Covers:
  * `/api/fleet/snapshot` with a seeded ring buffer.
  * `/api/fleet/categories` aggregates.
  * `/api/fleet/vessels` SSE: mock the upstream websocket source;
    collect events until a heartbeat is seen.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import fleet_service


def _seed_vessel(mmsi: int, flag: str, name: str | None = None) -> dict:
    return {
        "Vessel_Name": name or f"MMSI {mmsi}",
        "MMSI": mmsi,
        "Cargo_Volume_bbls": 1_400_000,
        "Destination": "unknown",
        "Flag_State": flag,
        "Latitude": 25.0,
        "Longitude": -90.0,
    }


@pytest.fixture(autouse=True)
def _reset_fleet_state():
    """Clear the ring buffer + subscribers between tests."""
    fleet_service.reset_state()
    yield
    fleet_service.reset_state()


def test_snapshot_returns_seeded_buffer():
    """`/api/fleet/snapshot` returns whatever the ring buffer holds."""
    fleet_service.ingest_for_test(_seed_vessel(366111111, "United States"))
    fleet_service.ingest_for_test(_seed_vessel(422111111, "Iran"))
    fleet_service.ingest_for_test(_seed_vessel(538111111, "Marshall Islands"))

    client = TestClient(create_app())
    resp = client.get("/api/fleet/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    mmsis = {v["MMSI"] for v in body["vessels"]}
    assert mmsis == {366111111, 422111111, 538111111}


def test_snapshot_buffer_caps_at_1000():
    """Ring buffer retains at most 1000 vessels (per-MMSI dedup)."""
    assert fleet_service.BUFFER_MAX == 1000
    for i in range(1500):
        fleet_service.ingest_for_test(_seed_vessel(300000000 + i, "Panama"))
    client = TestClient(create_app())
    resp = client.get("/api/fleet/snapshot")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1000


def test_categories_aggregates_flag_buckets():
    """`/api/fleet/categories` buckets vessels into policy categories."""
    fleet_service.ingest_for_test(_seed_vessel(366000001, "United States"))
    fleet_service.ingest_for_test(_seed_vessel(367000001, "United States"))
    fleet_service.ingest_for_test(_seed_vessel(636000001, "Liberia"))
    fleet_service.ingest_for_test(_seed_vessel(538000001, "Marshall Islands"))
    fleet_service.ingest_for_test(_seed_vessel(422000001, "Iran"))
    fleet_service.ingest_for_test(_seed_vessel(775000001, "Venezuela"))
    fleet_service.ingest_for_test(_seed_vessel(273000001, "Russia"))

    client = TestClient(create_app())
    resp = client.get("/api/fleet/categories")
    assert resp.status_code == 200
    body = resp.json()
    cats = body["categories"]
    assert set(cats.keys()) >= {
        "jones_act",
        "domestic",
        "shadow",
        "sanctioned",
    }
    assert cats["jones_act"]["count"] == 2
    assert cats["sanctioned"]["count"] == 3
    assert cats["shadow"]["count"] >= 2
    assert body["total"] == 7


def test_sse_emits_snapshot_then_heartbeat(monkeypatch):
    """SSE endpoint emits an initial snapshot event and at least one heartbeat.

    We test the event generator directly instead of via TestClient streaming
    because TestClient.stream holds the request open until the generator
    returns; sse-starlette's pings are infinite by design.
    """
    # Short heartbeat so the test is fast.
    monkeypatch.setattr(fleet_service, "HEARTBEAT_SECONDS", 0.05)
    fleet_service.ingest_for_test(_seed_vessel(366123456, "United States"))
    monkeypatch.setattr(fleet_service, "_ensure_producer_running", lambda: None)

    from backend.routers import fleet as fleet_router

    async def _drive():
        resp = await fleet_router.fleet_vessels_stream()
        body_iter = resp.body_iterator
        snapshot_seen = False
        timeout_seen = False
        for _ in range(6):
            try:
                ev = await asyncio.wait_for(body_iter.__anext__(), timeout=1.0)
            except StopAsyncIteration:
                break
            if isinstance(ev, dict):
                if ev.get("event") == "snapshot":
                    snapshot_seen = True
                if "comment" in ev:
                    timeout_seen = True
            else:
                text = str(ev)
                if "event: snapshot" in text:
                    snapshot_seen = True
                if re.search(r"^:\s", text, flags=re.MULTILINE):
                    timeout_seen = True
            if snapshot_seen and timeout_seen:
                break
        return snapshot_seen, timeout_seen

    loop = asyncio.new_event_loop()
    try:
        snapshot_seen, timeout_seen = loop.run_until_complete(_drive())
    finally:
        loop.close()
    assert snapshot_seen, "snapshot event not emitted"
    assert timeout_seen, "no heartbeat emitted after idle interval"

def test_delta_payload_is_valid_json():
    """Events emitted into subscriber queues serialise to JSON cleanly."""
    loop = asyncio.new_event_loop()
    try:
        q = loop.run_until_complete(fleet_service.subscribe())
        loop.run_until_complete(
            fleet_service.publish_delta(_seed_vessel(367000002, "United States"))
        )
        event = loop.run_until_complete(asyncio.wait_for(q.get(), timeout=1.0))
        payload = json.loads(json.dumps(event))
        assert payload["MMSI"] == 367000002
        loop.run_until_complete(fleet_service.unsubscribe(q))
    finally:
        loop.close()
