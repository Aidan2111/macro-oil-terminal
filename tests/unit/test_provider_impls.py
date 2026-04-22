"""Coverage for individual provider implementations — _yfinance, _fred, _aisstream.

These modules are gated on network or on API keys; we cover their happy
and failure paths via monkey-patched stand-ins.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# _yfinance
# ---------------------------------------------------------------------------
class _FakeYfDownload:
    def __init__(self, columns_multiindex: bool = True):
        self.columns_multiindex = columns_multiindex

    def __call__(self, *args, **kwargs):
        idx = pd.date_range("2024-01-01", periods=40, freq="D")
        rng = np.random.default_rng(1)
        wti = np.cumsum(rng.normal(0, 0.3, 40)) + 75.0
        brent = wti + 3.2 + np.cumsum(rng.normal(0, 0.05, 40))
        if self.columns_multiindex:
            cols = pd.MultiIndex.from_product([["Close"], ["BZ=F", "CL=F"]])
            return pd.DataFrame({("Close", "BZ=F"): brent, ("Close", "CL=F"): wti}, index=idx)
        return pd.DataFrame({"Close": brent}, index=idx)


class _FakeTicker:
    def __init__(self, ticker):
        self.ticker = ticker

    def history(self, period, interval, auto_adjust=False):
        idx = pd.date_range("2024-01-01", periods=30, freq="min")
        return pd.DataFrame({"Close": np.linspace(80.0, 82.0, 30)}, index=idx)


def test_yfinance_fetch_daily_happy(monkeypatch):
    import providers._yfinance as yfmod
    fake = _FakeYfDownload(columns_multiindex=True)
    monkeypatch.setattr(yfmod.yf, "download", fake)
    df = yfmod.fetch_daily(years=1)
    assert not df.empty
    assert {"Brent", "WTI"}.issubset(df.columns)


def test_yfinance_fetch_daily_empty_raises(monkeypatch):
    import providers._yfinance as yfmod

    def _empty(*a, **kw):
        return pd.DataFrame()
    monkeypatch.setattr(yfmod.yf, "download", _empty)
    with pytest.raises(RuntimeError):
        yfmod.fetch_daily(years=1)


def test_yfinance_fetch_intraday_happy(monkeypatch):
    import providers._yfinance as yfmod
    monkeypatch.setattr(yfmod.yf, "Ticker", _FakeTicker)
    df = yfmod.fetch_intraday()
    assert not df.empty
    assert {"Brent", "WTI"}.issubset(df.columns)


def test_yfinance_fetch_intraday_empty_raises(monkeypatch):
    import providers._yfinance as yfmod

    class _EmptyTicker:
        def __init__(self, t): pass
        def history(self, **kw):
            return pd.DataFrame()

    monkeypatch.setattr(yfmod.yf, "Ticker", _EmptyTicker)
    with pytest.raises(RuntimeError):
        yfmod.fetch_intraday()


# ---------------------------------------------------------------------------
# _fred
# ---------------------------------------------------------------------------
def test_fred_requires_key(monkeypatch):
    import providers._fred as fred
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        fred._fetch_series("WCESTUS1")


def test_fred_happy_path(monkeypatch):
    import providers._fred as fred
    monkeypatch.setenv("FRED_API_KEY", "stub")

    class _Resp:
        def __init__(self, payload):
            self._p = payload
        def raise_for_status(self): pass
        def json(self): return self._p

    def _fake_get(url, params=None, timeout=None):
        assert params["series_id"] in ("WCESTUS1", "WCSSTUS1")
        obs = [
            {"date": "2024-01-05", "value": "430000"},
            {"date": "2024-01-12", "value": "432500"},
            {"date": "2024-01-19", "value": "."},  # missing value → dropped
        ]
        return _Resp({"observations": obs})

    import requests
    monkeypatch.setattr(requests, "get", _fake_get)

    out = fred.fetch_inventory()
    assert not out.empty
    assert {"Commercial_bbls", "SPR_bbls", "Total_Inventory_bbls"}.issubset(out.columns)


# ---------------------------------------------------------------------------
# _aisstream (pure helpers — skip the async websocket)
# ---------------------------------------------------------------------------
def test_aisstream_flag_lookup():
    from providers._aisstream import _flag_from_mmsi
    assert _flag_from_mmsi(351000001) == "Panama"
    assert _flag_from_mmsi(366000001) == "United States"
    assert _flag_from_mmsi(422000001) == "Iran"
    assert _flag_from_mmsi(273000001) == "Russia"
    assert _flag_from_mmsi(111000001) == "Other"


def test_aisstream_requires_key(monkeypatch):
    from providers import _aisstream
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        _aisstream.fetch_snapshot(n_vessels=1, seconds=1)
