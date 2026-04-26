"""Tests for the fleet service fan-out.

The legacy `/api/fleet/*` route tests targeted the old `backend.routers.fleet`
module (now removed in the dead-code sweep). The canonical handlers in
`backend/main.py` are exercised at integration time via the smoke-import
gate in CI; the residual unit-level coverage here pins the queue fan-out
contract that both the SSE handler and the snapshot endpoint depend on.
"""

from __future__ import annotations

import asyncio
import json

import pytest

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
