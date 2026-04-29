"""Unit tests for the Russia mirror service (issue #82)."""

from __future__ import annotations

import json
import time

import pytest


def test_is_russian_flagged_handles_variants():
    from backend.services import russia_service as svc

    assert svc.is_russian_flagged("Russia") is True
    assert svc.is_russian_flagged("Russian Federation") is True
    assert svc.is_russian_flagged("Russia (Russian Federation)") is True
    assert svc.is_russian_flagged("RUSSIAN FEDERATION") is True
    assert svc.is_russian_flagged("") is False
    assert svc.is_russian_flagged("Liberia") is False
    assert svc.is_russian_flagged(None) is False


def test_in_any_russia_fence_bosphorus():
    from backend.services import russia_service as svc

    # Bosphorus center is at (41.0, 29.0).
    assert svc.in_any_russia_fence(41.0, 29.0) == "Bosphorus"
    # Just inside the 30nm radius — about 0.4 deg latitude.
    assert svc.in_any_russia_fence(41.4, 29.0) == "Bosphorus"


def test_in_any_russia_fence_novorossiysk():
    from backend.services import russia_service as svc

    assert svc.in_any_russia_fence(44.7, 37.8) == "Novorossiysk"


def test_in_any_russia_fence_primorsk():
    from backend.services import russia_service as svc

    assert svc.in_any_russia_fence(60.4, 28.6) == "Primorsk"


def test_in_any_russia_fence_outside():
    from backend.services import russia_service as svc

    # Houston, USA — definitely not in any Russia fence.
    assert svc.in_any_russia_fence(29.7, -95.3) is None
    # Garbage coordinates — rejected.
    assert svc.in_any_russia_fence(0.0, 0.0) is None
    assert svc.in_any_russia_fence(float("nan"), 29.0) is None


def test_record_daily_buckets_higher_water_mark(monkeypatch, tmp_path):
    from backend.services import russia_service as svc

    bucket = tmp_path / "russia_daily.jsonl"
    monkeypatch.setattr(svc, "_BUCKET_PATH", bucket)

    svc.record_daily_buckets(chokepoint_transits=5, exports=3, imports=1, today="2026-04-29")
    svc.record_daily_buckets(chokepoint_transits=7, exports=2, imports=4, today="2026-04-29")
    rows = [json.loads(line) for line in bucket.read_text().splitlines() if line.strip()]
    assert rows == [
        {"date": "2026-04-29", "chokepoint_transits": 7, "exports": 3, "imports": 4}
    ]


def test_percentile_vs_history_empty_returns_neutral(monkeypatch, tmp_path):
    from backend.services import russia_service as svc

    monkeypatch.setattr(svc, "_BUCKET_PATH", tmp_path / "russia_daily.jsonl")
    assert svc.percentile_vs_history(10) == 50.0


def test_compute_envelope_with_mocked_fleet(monkeypatch, tmp_path):
    from backend.services import fleet_service, ofac_service, russia_service as svc

    bucket = tmp_path / "russia_daily.jsonl"
    monkeypatch.setattr(svc, "_BUCKET_PATH", bucket)

    # Stub out OFAC to avoid the network call (issue #81 service is
    # already exercised by its own test file). Returns a payload with
    # russia delta = 4 so we can verify it bubbles through.
    def _ofac_envelope():
        return {
            "totals": {"iran": 0, "russia": 4, "venezuela": 0},
            "delta_vs_baseline": {"iran": 0, "russia": 4, "venezuela": 0},
        }
    monkeypatch.setattr(ofac_service, "compute_envelope", _ofac_envelope)

    now = time.time()
    monkeypatch.setattr(
        fleet_service,
        "_latest_by_mmsi",
        {
            # Russian flag at sea (not in any fence) → export.
            111: {
                "MMSI": 111, "Flag_State": "Russia",
                "Latitude": 50.0, "Longitude": 0.0,
                "Destination": "ROTTERDAM",
                "_ingested_at": now,
            },
            # Foreign flag inside Novorossiysk fence → import.
            222: {
                "MMSI": 222, "Flag_State": "Liberia",
                "Latitude": 44.7, "Longitude": 37.8,
                "Destination": "NOVOROSSIYSK",
                "_ingested_at": now,
            },
            # Russian flag inside Bosphorus → chokepoint, no export bucket
            # because in_chokepoint=True kills the export classification.
            333: {
                "MMSI": 333, "Flag_State": "Russia",
                "Latitude": 41.0, "Longitude": 29.0,
                "Destination": "ISTANBUL",
                "_ingested_at": now,
            },
            # Stale (>24h) — excluded.
            444: {
                "MMSI": 444, "Flag_State": "Russia",
                "Latitude": 50.0, "Longitude": 0.0,
                "_ingested_at": now - 25 * 3600,
            },
        },
    )

    env = svc.compute_envelope()
    # Vessel 222 + 333 are in fences → chokepoint = 2.
    assert env["chokepoint_transits_24h"] == 2
    # Vessel 111 is the only export.
    assert env["exports_today"] == 1
    # Vessel 222 is the only import.
    assert env["imports_today"] == 1
    assert env["sanctions_delta_30d"] == 4
    state = svc.get_last_fetch_state()
    assert state["status"] == "green"
