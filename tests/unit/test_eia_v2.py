"""Coverage for the EIA v2 API path in providers/_eia.py.

The v2 endpoint is key-gated; these tests monkey-patch ``requests.get``
to verify the contract without hitting the network. A separate CI-only
real-call integration test lives at the bottom (gated on $CI + $EIA_API_KEY).
"""

from __future__ import annotations

import os

import pandas as pd
import pytest


def _fake_v2_response(rows):
    """Return a minimal v2-shaped JSON given a list of (period, value) tuples."""
    class _Resp:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "response": {
                    "data": [{"period": p, "value": v} for (p, v) in rows],
                    "warnings": [],
                }
            }
    return _Resp()


class _FakeGet:
    def __init__(self, rows):
        self.rows = rows
        self.last_url = None
        self.calls = 0

    def __call__(self, url, params=None, timeout=None):
        self.last_url = url
        self.calls += 1
        return _fake_v2_response(self.rows)


@pytest.fixture(autouse=True)
def _reset_cache():
    from providers import _eia
    _eia._V2_CACHE.clear()
    yield
    _eia._V2_CACHE.clear()


def test_v2_happy_path(monkeypatch):
    """When EIA_API_KEY is set, _fetch_series_v2 parses the v2 JSON payload."""
    from providers import _eia

    monkeypatch.setenv("EIA_API_KEY", "fake-test-key")
    rows = [
        ("2024-01-05", 400_000),
        ("2024-01-12", 405_000),
        ("2024-01-19", 402_500),
    ]
    fake = _FakeGet(rows)
    monkeypatch.setattr("providers._eia.requests.get", fake)

    series = _eia._fetch_series_v2("WCESTUS1")
    # v2 endpoint must have received the transformed PET.WCESTUS1.W path
    assert fake.last_url.endswith("PET.WCESTUS1.W")
    # Values converted from Mbbl -> bbl (x1000). Series is sorted ascending so
    # the final row is the most recent date (2024-01-19 = 402_500 * 1000).
    assert series.iloc[-1] == pytest.approx(402_500_000.0)
    assert len(series) == 3
    assert series.index.is_monotonic_increasing


def test_v2_cache_hit_avoids_second_call(monkeypatch):
    from providers import _eia

    monkeypatch.setenv("EIA_API_KEY", "fake-test-key")
    fake = _FakeGet([("2024-02-02", 410_000)])
    monkeypatch.setattr("providers._eia.requests.get", fake)

    _eia._fetch_series_v2("WCESTUS1")
    _eia._fetch_series_v2("WCESTUS1")  # should hit cache
    assert fake.calls == 1


def test_v2_missing_key_raises(monkeypatch):
    from providers import _eia
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="EIA_API_KEY not set"):
        _eia._fetch_series_v2("WCESTUS1")


def test_v2_forbidden_raises(monkeypatch):
    from providers import _eia
    monkeypatch.setenv("EIA_API_KEY", "bad-key")

    class _Forbidden:
        status_code = 403
        text = "forbidden"
        def raise_for_status(self):
            raise RuntimeError("403 forbidden")
        def json(self):
            return {}

    monkeypatch.setattr(
        "providers._eia.requests.get",
        lambda url, params=None, timeout=None: _Forbidden(),
    )
    with pytest.raises(RuntimeError, match="forbidden"):
        _eia._fetch_series_v2("WCESTUS1")


def test_v2_empty_data_raises(monkeypatch):
    from providers import _eia
    monkeypatch.setenv("EIA_API_KEY", "fake")

    class _Empty:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"response": {"data": []}}

    monkeypatch.setattr(
        "providers._eia.requests.get",
        lambda url, params=None, timeout=None: _Empty(),
    )
    with pytest.raises(RuntimeError, match="empty data"):
        _eia._fetch_series_v2("WCESTUS1")


def test_active_mode_reflects_key(monkeypatch):
    from providers import _eia
    monkeypatch.setenv("EIA_API_KEY", "x")
    assert "v2 API" in _eia.active_mode()
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    assert "dnav" in _eia.active_mode()


def test_fetch_inventory_schema_via_v2(monkeypatch):
    """End-to-end: fetch_inventory should populate all four canonical columns."""
    from providers import _eia
    monkeypatch.setenv("EIA_API_KEY", "x")

    def _rows_for(series):
        # Build synthetic data differing per series so we can tell them apart
        base = {"WCESTUS1": 400, "WCSSTUS1": 350, "W_EPC0_SAX_YCUOK_MBBL": 30}[series.split(".")[1] if series.startswith("PET.") else series]
        return [
            (f"2024-0{m}-05", base + m * 5) for m in range(1, 6)
        ]

    def fake_get(url, params=None, timeout=None):
        for s in ("WCESTUS1", "WCSSTUS1", "W_EPC0_SAX_YCUOK_MBBL"):
            if s in url:
                return _fake_v2_response(_rows_for(s))
        return _fake_v2_response([])

    monkeypatch.setattr("providers._eia.requests.get", fake_get)
    df = _eia.fetch_inventory(start=None)
    assert {"Commercial_bbls", "SPR_bbls", "Cushing_bbls", "Total_Inventory_bbls"}.issubset(df.columns)
    assert not df.empty
    assert (df["Total_Inventory_bbls"] > 0).all()


# ---------------------------------------------------------------------------
# Real-call integration test — runs only in CI with the real key
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not (os.getenv("CI") and os.getenv("EIA_API_KEY")),
    reason="real-call EIA integration only runs in CI with EIA_API_KEY set",
)
def test_v2_live_integration_smoke():
    """One real call to verify the live key works against production EIA v2."""
    from providers import _eia
    series = _eia._fetch_series_v2("WCESTUS1")
    assert len(series) > 100
    # Values are in barrels; commercial US stocks are always > 100M bbl
    assert float(series.iloc[-1]) > 100_000_000
