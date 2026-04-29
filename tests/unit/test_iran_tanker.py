"""Unit tests for the Iranian-flagged + Iran-destined tanker counter (issue #78)."""

from __future__ import annotations

import json
import time

import pytest


def test_is_iranian_flagged_handles_variants():
    from backend.services import iran_tanker_service as svc

    assert svc.is_iranian_flagged("Iran (Islamic Republic of)") is True
    assert svc.is_iranian_flagged("iran islamic republic of") is True
    assert svc.is_iranian_flagged("Islamic Republic of Iran") is True
    assert svc.is_iranian_flagged("Iran") is True
    assert svc.is_iranian_flagged("  IRAN  ") is True


def test_is_iranian_flagged_rejects_non_iran():
    from backend.services import iran_tanker_service as svc

    assert svc.is_iranian_flagged("Russia") is False
    assert svc.is_iranian_flagged("Saudi Arabia") is False
    assert svc.is_iranian_flagged("") is False
    assert svc.is_iranian_flagged(None) is False


def test_is_iran_bound_matches_known_ports():
    from backend.services import iran_tanker_service as svc

    assert svc.is_iran_bound("BANDAR ABBAS") is True
    assert svc.is_iran_bound("Kharg Island") is True
    assert svc.is_iran_bound("Asaluyeh") is True
    # Substring within a longer string still matches.
    assert svc.is_iran_bound("BANDAR-E IMAM KHOMEINI") is True
    assert svc.is_iran_bound("Siri Island Terminal") is True


def test_is_iran_bound_rejects_other_destinations():
    from backend.services import iran_tanker_service as svc

    assert svc.is_iran_bound("ROTTERDAM") is False
    assert svc.is_iran_bound("HOUSTON") is False
    assert svc.is_iran_bound("") is False
    assert svc.is_iran_bound(None) is False


def test_classify_vessel_export_path():
    from backend.services import iran_tanker_service as svc

    v = {"Flag_State": "Iran", "Destination": "ROTTERDAM"}
    assert svc.classify_vessel(v) == "iran_export"


def test_classify_vessel_import_path():
    from backend.services import iran_tanker_service as svc

    v = {"Flag_State": "Panama", "Destination": "BANDAR ABBAS"}
    assert svc.classify_vessel(v) == "iran_import"


def test_classify_vessel_iranian_flag_iranian_dest_counts_as_import():
    from backend.services import iran_tanker_service as svc

    v = {"Flag_State": "Iran", "Destination": "BANDAR ABBAS"}
    assert svc.classify_vessel(v) == "iran_import"


def test_classify_vessel_neither_returns_none():
    from backend.services import iran_tanker_service as svc

    v = {"Flag_State": "Liberia", "Destination": "ROTTERDAM"}
    assert svc.classify_vessel(v) is None


def test_record_daily_buckets_higher_water_mark(monkeypatch, tmp_path):
    from backend.services import iran_tanker_service as svc

    bucket = tmp_path / "iran_tankers_daily.jsonl"
    monkeypatch.setattr(svc, "_BUCKET_PATH", bucket)

    svc.record_daily_buckets(exports=2, imports=1, today="2026-04-29")
    svc.record_daily_buckets(exports=1, imports=3, today="2026-04-29")  # higher import wins
    rows = [json.loads(line) for line in bucket.read_text().splitlines() if line.strip()]
    assert rows == [{"date": "2026-04-29", "exports": 2, "imports": 3}]


def test_rolling_totals_sums_last_7_days(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone

    from backend.services import iran_tanker_service as svc

    bucket = tmp_path / "iran_tankers_daily.jsonl"
    bucket.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    rows = []
    for i in range(10):
        d = (today - timedelta(days=i)).isoformat()
        rows.append({"date": d, "exports": 1, "imports": 2})
    bucket.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(svc, "_BUCKET_PATH", bucket)

    totals = svc.rolling_totals(days=7)
    assert totals == {"exports": 7, "imports": 14}


def test_compute_envelope_filters_via_fleet_service(monkeypatch, tmp_path):
    from backend.services import fleet_service, iran_tanker_service as svc

    bucket = tmp_path / "iran_tankers_daily.jsonl"
    monkeypatch.setattr(svc, "_BUCKET_PATH", bucket)

    now = time.time()
    monkeypatch.setattr(
        fleet_service,
        "_latest_by_mmsi",
        {
            # Iran-flagged exporting — counts as export.
            111: {
                "MMSI": 111, "Flag_State": "Iran",
                "Destination": "ROTTERDAM",
                "_ingested_at": now,
            },
            # Heading to BANDAR ABBAS — counts as import.
            222: {
                "MMSI": 222, "Flag_State": "Liberia",
                "Destination": "BANDAR ABBAS",
                "_ingested_at": now,
            },
            # Stale (>24h) — excluded.
            333: {
                "MMSI": 333, "Flag_State": "Iran",
                "Destination": "GREECE",
                "_ingested_at": now - 25 * 3600,
            },
            # Irrelevant — neither flag nor destination matches.
            444: {
                "MMSI": 444, "Flag_State": "Russia",
                "Destination": "MURMANSK",
                "_ingested_at": now,
            },
        },
    )

    env = svc.compute_envelope()
    assert env["exports_today"] == 1
    assert env["imports_today"] == 1
    assert env["exports_7d"] == 1
    assert env["imports_7d"] == 1
    assert len(env["latest_vessels"]) == 2

    state = svc.get_last_fetch_state()
    assert state["status"] == "green"
    assert state["n_obs"] == 2  # exports + imports
