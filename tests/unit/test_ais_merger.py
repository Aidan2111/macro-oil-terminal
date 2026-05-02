"""Issue #107 — AIS multi-source merger unit tests.

Acceptance:
  * Two buffers merge with MMSI dedup; freshest _ingested_at wins.
  * Single buffer is a passthrough (no extra cost when secondary unconfigured).
  * Each output carries _source so /api/data-quality can attribute.
"""

from __future__ import annotations

import pytest

from backend.services.ais_merger import (
    is_secondary_enabled,
    merge_stats,
    merge_vessel_buffers,
    secondary_provider_tag,
)


def _v(mmsi: int, *, name: str = "Tanker", ts: float = 0.0,
       source: str | None = None) -> dict:
    out = {
        "MMSI": mmsi,
        "Vessel_Name": name,
        "Cargo_Volume_bbls": 1_400_000,
        "Destination": "unknown",
        "Flag_State": "Other",
        "Latitude": 26.5,
        "Longitude": 56.3,
        "_ingested_at": ts,
    }
    if source is not None:
        out["_source"] = source
    return out


# ---------------------------------------------------------------------------
# Pure dedup logic
# ---------------------------------------------------------------------------
def test_single_buffer_passthrough():
    a = [_v(100, ts=1.0), _v(101, ts=2.0)]
    out = merge_vessel_buffers(a, source_tags=("aisstream",))
    assert len(out) == 2
    # _source stamped from the tag
    assert all(v["_source"] == "aisstream" for v in out)


def test_two_buffers_dedup_by_mmsi_freshest_wins():
    a = [_v(100, ts=1000.0)]
    b = [_v(100, ts=2000.0, name="LATER")]  # newer
    out = merge_vessel_buffers(a, b, source_tags=("aisstream", "fleetmon"))
    assert len(out) == 1
    assert out[0]["Vessel_Name"] == "LATER"
    assert out[0]["_source"] == "fleetmon"


def test_two_buffers_dedup_when_primary_is_fresher():
    a = [_v(100, ts=2000.0, name="PRIMARY")]
    b = [_v(100, ts=1000.0, name="SECONDARY")]
    out = merge_vessel_buffers(a, b, source_tags=("aisstream", "fleetmon"))
    assert len(out) == 1
    assert out[0]["Vessel_Name"] == "PRIMARY"
    assert out[0]["_source"] == "aisstream"


def test_disjoint_buffers_pool_into_union():
    a = [_v(100, ts=1.0), _v(101, ts=1.0)]
    b = [_v(200, ts=1.0), _v(201, ts=1.0)]
    out = merge_vessel_buffers(a, b, source_tags=("aisstream", "fleetmon"))
    assert len(out) == 4
    mmsis = sorted(v["MMSI"] for v in out)
    assert mmsis == [100, 101, 200, 201]


def test_tie_broken_by_buffer_order():
    """Same _ingested_at — earlier buffer wins."""
    a = [_v(100, ts=42.0, name="PRIMARY_TIE")]
    b = [_v(100, ts=42.0, name="SECONDARY_TIE")]
    out = merge_vessel_buffers(a, b, source_tags=("aisstream", "fleetmon"))
    assert len(out) == 1
    assert out[0]["Vessel_Name"] == "PRIMARY_TIE"


def test_vessel_without_mmsi_dropped():
    a = [{"Vessel_Name": "no-mmsi"}, _v(100, ts=1.0)]
    out = merge_vessel_buffers(a, source_tags=("aisstream",))
    assert len(out) == 1
    assert out[0]["MMSI"] == 100


def test_existing_source_tag_preserved():
    a = [_v(100, ts=1.0, source="manually-tagged")]
    out = merge_vessel_buffers(a, source_tags=("aisstream",))
    assert out[0]["_source"] == "manually-tagged"


def test_three_or_more_buffers_supported():
    a = [_v(100, ts=1.0)]
    b = [_v(200, ts=1.0)]
    c = [_v(300, ts=1.0)]
    out = merge_vessel_buffers(a, b, c, source_tags=("aisstream", "fleetmon", "spire"))
    assert len(out) == 3
    sources = sorted(v["_source"] for v in out)
    assert sources == ["aisstream", "fleetmon", "spire"]


def test_empty_input_returns_empty_list():
    assert merge_vessel_buffers([], source_tags=("aisstream",)) == []
    assert merge_vessel_buffers([], [], source_tags=("aisstream", "fleetmon")) == []


# ---------------------------------------------------------------------------
# Stats helper
# ---------------------------------------------------------------------------
def test_merge_stats_counts_per_source():
    a = [_v(100, ts=1.0), _v(101, ts=1.0)]
    b = [_v(200, ts=2.0)]
    out = merge_vessel_buffers(a, b, source_tags=("aisstream", "fleetmon"))
    stats = merge_stats(out)
    assert stats == {"aisstream": 2, "fleetmon": 1}


# ---------------------------------------------------------------------------
# Env-var gating
# ---------------------------------------------------------------------------
def test_is_secondary_enabled_off_by_default(monkeypatch):
    monkeypatch.delenv("AIS_SECONDARY_ENABLED", raising=False)
    assert is_secondary_enabled() is False


def test_is_secondary_enabled_truthy_values(monkeypatch):
    for v in ("1", "true", "True", "yes", "on"):
        monkeypatch.setenv("AIS_SECONDARY_ENABLED", v)
        assert is_secondary_enabled() is True, f"{v!r} should enable"


def test_secondary_provider_tag_round_trip(monkeypatch):
    monkeypatch.delenv("AIS_SECONDARY_PROVIDER", raising=False)
    assert secondary_provider_tag() is None
    monkeypatch.setenv("AIS_SECONDARY_PROVIDER", "fleetmon")
    assert secondary_provider_tag() == "fleetmon"


# ---------------------------------------------------------------------------
# DQ shim
# ---------------------------------------------------------------------------
def test_ais_secondary_service_amber_when_disabled(monkeypatch):
    monkeypatch.delenv("AIS_SECONDARY_ENABLED", raising=False)
    from backend.services import ais_secondary_service

    state = ais_secondary_service.get_last_fetch_state()
    assert state["status"] == "amber"
    assert state["last_good_at"] is None
    assert "disabled" in str(state.get("message", "")).lower()


def test_ais_secondary_service_records_when_enabled(monkeypatch):
    monkeypatch.setenv("AIS_SECONDARY_ENABLED", "1")
    from backend.services import ais_secondary_service

    ais_secondary_service.record_fetch_success(n_obs=88, latency_ms=42)
    state = ais_secondary_service.get_last_fetch_state()
    assert state["status"] == "green"
    assert state["n_obs"] == 88
    assert state["last_good_at"] is not None
