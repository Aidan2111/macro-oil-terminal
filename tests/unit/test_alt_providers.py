"""Tests for Twelve Data + Polygon + aggregated health panel."""

from __future__ import annotations

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Twelve Data
# ---------------------------------------------------------------------------
def test_twelvedata_requires_key(monkeypatch):
    from providers import _twelvedata as td
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        td._fetch_symbol("BRN/USD", "1day", 10)


def test_twelvedata_happy_path(monkeypatch):
    from providers import _twelvedata as td
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "stub")

    class _Resp:
        def __init__(self, body):
            self._b = body
        def raise_for_status(self): pass
        def json(self): return self._b

    def _fake_get(url, params=None, timeout=None):
        sym = params["symbol"]
        vals = [
            {"datetime": "2024-01-05", "close": "77.00"} if sym == "WTI/USD" else {"datetime": "2024-01-05", "close": "80.50"},
            {"datetime": "2024-01-04", "close": "76.50"} if sym == "WTI/USD" else {"datetime": "2024-01-04", "close": "80.00"},
        ]
        return _Resp({"status": "ok", "values": vals})

    import requests
    monkeypatch.setattr(requests, "get", _fake_get)

    df = td.fetch_daily(years=1)
    assert not df.empty
    assert {"Brent", "WTI"}.issubset(df.columns)


def test_twelvedata_error_body_raises(monkeypatch):
    from providers import _twelvedata as td
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "stub")

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"status": "error", "message": "bad"}

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _Resp())
    with pytest.raises(RuntimeError):
        td._fetch_symbol("BRN/USD", "1day", 10)


def test_twelvedata_health_without_key(monkeypatch):
    from providers import _twelvedata as td
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    out = td.health_check()
    assert out["ok"] is False
    assert "api key" in out["note"].lower()


# ---------------------------------------------------------------------------
# Polygon
# ---------------------------------------------------------------------------
def test_polygon_requires_key(monkeypatch):
    from providers import _polygon as pg
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        pg._fetch("C:BRN1!", "2024-01-01", "2024-01-05")


def test_polygon_health_without_key(monkeypatch):
    from providers import _polygon as pg
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    out = pg.health_check()
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# Orchestrator + health panel
# ---------------------------------------------------------------------------
def test_pricing_falls_through_to_twelvedata(monkeypatch):
    import providers.pricing as pp
    from providers import _yfinance as yfm, _twelvedata as td
    monkeypatch.setattr(yfm, "fetch_daily", lambda years=5: (_ for _ in ()).throw(RuntimeError("yfinance down")))

    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    frame = pd.DataFrame({"Brent": range(80, 110), "WTI": range(78, 108)}, index=idx)
    monkeypatch.setattr(td, "fetch_daily", lambda years=5: frame)
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "stub")

    res = pp.fetch_pricing_daily(years=1)
    assert res.source == "Twelve Data"
    assert not res.frame.empty


def test_providers_health_returns_known_labels(monkeypatch):
    # Force skip paths so health_check probes don't hit the network
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)

    # Short-circuit the two real-network probes too
    import providers.health as ph
    import providers._yfinance as yfm
    monkeypatch.setattr(yfm, "health_check", lambda timeout=6.0: {"ok": True, "latency_ms": 5, "note": "stub"})
    import requests
    def _fake_get(url, params=None, timeout=None):
        class _R:
            status_code = 200
            text = "a" * 20000
            @property
            def elapsed(self):
                import datetime
                return datetime.timedelta(milliseconds=3)
        return _R()
    monkeypatch.setattr(requests, "get", _fake_get)

    rows = ph.providers_health()
    labels = [r["label"] for r in rows]
    for label in (
        "yfinance (pricing)",
        "Twelve Data (pricing)",
        "Polygon.io (pricing)",
        "EIA dnav (inventory)",
        "FRED API (inventory fallback)",
        "aisstream.io (AIS)",
        "CFTC disaggregated (positioning)",
    ):
        assert label in labels
    # At least yfinance + EIA should be ok=True (both mocked)
    assert sum(1 for r in rows if r["ok"] is True) >= 2
    # Providers without keys are ok=None, not False
    skipped = [r for r in rows if "not set" in r["note"]]
    assert all(r["ok"] is None for r in skipped)
