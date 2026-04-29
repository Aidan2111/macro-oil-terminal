"""Unit tests for the Strait of Hormuz tanker transit counter (issue #77)."""

from __future__ import annotations

import json
import pathlib

import pytest


def test_hormuz_center_is_inside_fence():
    from backend.services.geopolitical_service import is_in_hormuz_fence

    assert is_in_hormuz_fence(26.5, 56.3) is True


def test_point_within_50nm_is_inside():
    from backend.services.geopolitical_service import is_in_hormuz_fence

    # ~10 nm north of center — well within the 50 nm radius.
    # 1 deg latitude ≈ 60 nm, so 10/60 ≈ 0.167 deg.
    assert is_in_hormuz_fence(26.5 + 0.167, 56.3) is True


def test_point_just_inside_radius():
    from backend.services.geopolitical_service import is_in_hormuz_fence

    # 49 nm due east of center — just inside the 50 nm radius.
    # At lat 26.5°, 1 deg longitude ≈ 60 * cos(26.5°) ≈ 53.7 nm.
    # So 49 nm ≈ 49 / 53.7 ≈ 0.913 deg longitude.
    assert is_in_hormuz_fence(26.5, 56.3 + 0.913) is True


def test_point_just_outside_radius():
    from backend.services.geopolitical_service import is_in_hormuz_fence

    # ~120 nm due east — well outside the 50 nm radius.
    assert is_in_hormuz_fence(26.5, 56.3 + 2.5) is False


def test_far_away_point_is_outside():
    from backend.services.geopolitical_service import is_in_hormuz_fence

    # New York Harbor — definitely not in Hormuz.
    assert is_in_hormuz_fence(40.7, -74.0) is False


def test_zero_zero_placeholder_is_rejected():
    """AIS feeds sometimes emit (0.0, 0.0) as a missing-position
    placeholder. Treat that as 'not in fence' to avoid the gulf of
    guinea-vs-strait confusion."""
    from backend.services.geopolitical_service import is_in_hormuz_fence

    assert is_in_hormuz_fence(0.0, 0.0) is False


def test_non_finite_inputs_are_rejected():
    from backend.services.geopolitical_service import is_in_hormuz_fence

    assert is_in_hormuz_fence(float("nan"), 56.3) is False
    assert is_in_hormuz_fence(26.5, float("inf")) is False


def test_string_inputs_coerce_or_reject():
    from backend.services.geopolitical_service import is_in_hormuz_fence

    # Decimal string at center.
    assert is_in_hormuz_fence("26.5", "56.3") is True
    # Garbage strings.
    assert is_in_hormuz_fence("not-a-number", 56.3) is False


def test_count_24h_filters_to_fenced_vessels(monkeypatch):
    """count_24h_transits walks fleet_service._latest_by_mmsi and
    returns only the vessels inside the geofence with a recent
    `_ingested_at` timestamp."""
    import time

    from backend.services import fleet_service, geopolitical_service

    now = time.time()
    monkeypatch.setattr(
        fleet_service,
        "_latest_by_mmsi",
        {
            # Inside the fence + recent — counts.
            111: {"MMSI": 111, "Latitude": 26.5, "Longitude": 56.3, "_ingested_at": now},
            # Inside the fence but >24h old — excluded.
            222: {"MMSI": 222, "Latitude": 26.6, "Longitude": 56.4,
                  "_ingested_at": now - 25 * 3600},
            # Outside the fence — excluded.
            333: {"MMSI": 333, "Latitude": 0.0, "Longitude": 0.0, "_ingested_at": now},
            # Inside the fence + recent — counts.
            444: {"MMSI": 444, "Latitude": 26.7, "Longitude": 56.2, "_ingested_at": now},
        },
    )

    assert geopolitical_service.count_24h_transits() == 2


def test_record_daily_count_writes_jsonl_row(tmp_path, monkeypatch):
    from backend.services import geopolitical_service

    bucket = tmp_path / "hormuz_daily.jsonl"
    monkeypatch.setattr(geopolitical_service, "_BUCKET_PATH", bucket)

    geopolitical_service.record_daily_count(7, today="2026-04-28")
    rows = [json.loads(line) for line in bucket.read_text().splitlines() if line.strip()]
    assert rows == [{"date": "2026-04-28", "count": 7}]


def test_record_daily_count_overwrites_higher_water_mark(tmp_path, monkeypatch):
    """Calling record_daily_count multiple times in the same UTC day
    should keep the highest seen count, not append duplicate rows."""
    from backend.services import geopolitical_service

    bucket = tmp_path / "hormuz_daily.jsonl"
    monkeypatch.setattr(geopolitical_service, "_BUCKET_PATH", bucket)

    geopolitical_service.record_daily_count(5, today="2026-04-28")
    geopolitical_service.record_daily_count(3, today="2026-04-28")  # lower — kept at 5
    geopolitical_service.record_daily_count(8, today="2026-04-28")  # higher — wins

    rows = [json.loads(line) for line in bucket.read_text().splitlines() if line.strip()]
    assert rows == [{"date": "2026-04-28", "count": 8}]


def test_percentile_vs_history_with_empty_history_is_neutral(tmp_path, monkeypatch):
    from backend.services import geopolitical_service

    bucket = tmp_path / "hormuz_daily.jsonl"
    monkeypatch.setattr(geopolitical_service, "_BUCKET_PATH", bucket)

    # No history yet — percentile is 50 (neutral) so the UI doesn't
    # paint red on a fresh deploy.
    assert geopolitical_service.percentile_vs_history(7) == 50.0


def test_percentile_vs_history_ranks_count_against_buckets(tmp_path, monkeypatch):
    from backend.services import geopolitical_service

    bucket = tmp_path / "hormuz_daily.jsonl"
    bucket.parent.mkdir(parents=True, exist_ok=True)
    bucket.write_text(
        "\n".join(
            json.dumps({"date": f"2026-04-{i:02d}", "count": c})
            for i, c in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], start=1)
        )
        + "\n"
    )
    monkeypatch.setattr(geopolitical_service, "_BUCKET_PATH", bucket)

    # 7 is bigger than 6 prior entries (1..6), so percentile = 60.0.
    assert geopolitical_service.percentile_vs_history(7) == 60.0


def test_compute_envelope_returns_expected_shape(tmp_path, monkeypatch):
    """End-to-end shape check — `compute_envelope` returns the dict
    `/api/geopolitical/hormuz` ships."""
    from backend.services import fleet_service, geopolitical_service

    bucket = tmp_path / "hormuz_daily.jsonl"
    monkeypatch.setattr(geopolitical_service, "_BUCKET_PATH", bucket)
    monkeypatch.setattr(fleet_service, "_latest_by_mmsi", {})

    env = geopolitical_service.compute_envelope()
    assert set(env.keys()) == {"count_24h", "percentile_1y", "trend_30d"}
    assert env["count_24h"] == 0
    assert isinstance(env["percentile_1y"], float)
    assert len(env["trend_30d"]) == 30
    assert all(set(p.keys()) == {"date", "count"} for p in env["trend_30d"])
