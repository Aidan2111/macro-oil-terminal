"""Targeted coverage-gap tests for core modules.

Keeps behaviour-focused tests together but exists to push coverage on
error paths, branch edges, and happy paths that only network-gated
providers exercise.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# providers/pricing.py — fall-through branches
# ---------------------------------------------------------------------------
def test_pricing_all_providers_fail_raises(monkeypatch):
    import providers.pricing as pp
    from providers import _yfinance as yf, _twelvedata as td, _polygon as pg

    def _boom(*a, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr(yf, "fetch_daily", _boom)
    monkeypatch.setattr(td, "fetch_daily", _boom)
    monkeypatch.setattr(pg, "fetch_daily", _boom)
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "stub")
    monkeypatch.setenv("POLYGON_API_KEY", "stub")

    with pytest.raises(pp.PricingUnavailable):
        pp.fetch_pricing_daily(years=1)


def test_pricing_intraday_unavailable_raises(monkeypatch):
    import providers.pricing as pp
    from providers import _yfinance as yf

    monkeypatch.setattr(yf, "fetch_intraday", lambda interval="1m", period="2d": (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(pp.PricingUnavailable):
        pp.fetch_pricing_intraday()


# ---------------------------------------------------------------------------
# providers/_polygon.py — happy path with a mocked requests.get
# ---------------------------------------------------------------------------
def test_polygon_happy_path(monkeypatch):
    from providers import _polygon as pg
    monkeypatch.setenv("POLYGON_API_KEY", "stub")

    class _R:
        def raise_for_status(self): pass
        def json(self):
            return {
                "status": "OK",
                "results": [
                    {"t": 1_700_000_000_000, "c": 80.1},
                    {"t": 1_700_086_400_000, "c": 80.3},
                    {"t": 1_700_172_800_000, "c": 80.6},
                ],
            }

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _R())

    s = pg._fetch("C:BRN1!", "2023-11-14", "2023-11-16")
    assert len(s) == 3


def test_polygon_fetch_daily_combines_brent_wti(monkeypatch):
    from providers import _polygon as pg
    monkeypatch.setenv("POLYGON_API_KEY", "stub")

    def _fake_fetch(ticker, frm, to):
        idx = pd.date_range("2024-01-01", periods=10, freq="D")
        return pd.Series(np.linspace(80.0, 82.0, 10), index=idx, name=ticker)

    monkeypatch.setattr(pg, "_fetch", _fake_fetch)
    df = pg.fetch_daily(years=1)
    assert {"Brent", "WTI"}.issubset(df.columns)


def test_polygon_error_body_raises(monkeypatch):
    from providers import _polygon as pg
    monkeypatch.setenv("POLYGON_API_KEY", "stub")

    class _R:
        def raise_for_status(self): pass
        def json(self): return {"status": "ERROR", "error": "bad"}

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _R())
    with pytest.raises(RuntimeError):
        pg._fetch("C:BRN1!", "2024-01-01", "2024-01-05")


def test_polygon_health_with_key_ok(monkeypatch):
    from providers import _polygon as pg
    monkeypatch.setenv("POLYGON_API_KEY", "stub")

    class _R:
        status_code = 200

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _R())
    out = pg.health_check()
    assert out["ok"] is True


def test_polygon_health_non_200(monkeypatch):
    from providers import _polygon as pg
    monkeypatch.setenv("POLYGON_API_KEY", "stub")

    class _R:
        status_code = 500

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _R())
    out = pg.health_check()
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# providers/_twelvedata.py — intraday + health-ok branches
# ---------------------------------------------------------------------------
def test_twelvedata_intraday_mock(monkeypatch):
    from providers import _twelvedata as td
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "stub")

    def _fake_symbol(symbol, interval, outputsize):
        idx = pd.date_range("2024-01-01", periods=20, freq="min")
        return pd.Series(np.linspace(80.0, 81.0, 20), index=idx, name=symbol)

    monkeypatch.setattr(td, "_fetch_symbol", _fake_symbol)
    df = td.fetch_intraday()
    assert {"Brent", "WTI"}.issubset(df.columns)


def test_twelvedata_health_ok(monkeypatch):
    from providers import _twelvedata as td
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "stub")

    class _R:
        status_code = 200
        def json(self): return {"values": [{"datetime": "2024-01-01", "close": "80"}]}

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _R())
    out = td.health_check()
    assert out["ok"] is True


# ---------------------------------------------------------------------------
# providers/_yfinance.py — health + intraday branches
# ---------------------------------------------------------------------------
def test_yfinance_health_mocked(monkeypatch):
    from providers import _yfinance as yfm

    class _T:
        def __init__(self, t): self.t = t
        def history(self, **kw):
            idx = pd.date_range("2024-01-01", periods=2, freq="D")
            return pd.DataFrame({"Close": [80.0, 80.5]}, index=idx)

    monkeypatch.setattr(yfm.yf, "Ticker", _T)
    out = yfm.health_check()
    assert out["ok"] is True
    assert out["latency_ms"] >= 0


# ---------------------------------------------------------------------------
# trade_thesis — boundary + edge paths for materiality + diffs
# ---------------------------------------------------------------------------
def test_materiality_brent_price_shift(sample_ctx):
    from trade_thesis import _materiality_fingerprint, context_changed_materially
    prev = _materiality_fingerprint(sample_ctx)
    # >1.5% Brent move should trigger
    shifted = sample_ctx.__class__(**{**sample_ctx.__dict__, "latest_brent": sample_ctx.latest_brent * 1.03})
    cur = _materiality_fingerprint(shifted)
    reasons = context_changed_materially(prev, cur)
    assert any("brent" in r.lower() for r in reasons)


def test_materiality_wti_price_shift(sample_ctx):
    from trade_thesis import _materiality_fingerprint, context_changed_materially
    prev = _materiality_fingerprint(sample_ctx)
    shifted = sample_ctx.__class__(**{**sample_ctx.__dict__, "latest_wti": sample_ctx.latest_wti * 1.03})
    cur = _materiality_fingerprint(shifted)
    reasons = context_changed_materially(prev, cur)
    assert any("wti" in r.lower() for r in reasons)


def test_materiality_inventory_slope_sign_flip(sample_ctx):
    from trade_thesis import _materiality_fingerprint, context_changed_materially
    prev_ctx = sample_ctx.__class__(**{**sample_ctx.__dict__, "inventory_4w_slope_bbls_per_day": -100_000.0})
    cur_ctx = sample_ctx.__class__(**{**sample_ctx.__dict__, "inventory_4w_slope_bbls_per_day": +100_000.0})
    prev = _materiality_fingerprint(prev_ctx)
    cur = _materiality_fingerprint(cur_ctx)
    reasons = context_changed_materially(prev, cur)
    assert any("slope" in r.lower() or "sign" in r.lower() for r in reasons)


def test_materiality_new_eia_release_detected(sample_ctx):
    from trade_thesis import _materiality_fingerprint, context_changed_materially
    prev_ctx = sample_ctx.__class__(**{**sample_ctx.__dict__, "inventory_current_bbls": 800e6})
    cur_ctx = sample_ctx.__class__(**{**sample_ctx.__dict__, "inventory_current_bbls": 820e6})
    prev = _materiality_fingerprint(prev_ctx)
    cur = _materiality_fingerprint(cur_ctx)
    reasons = context_changed_materially(prev, cur)
    assert any("eia" in r.lower() or "inventory" in r.lower() for r in reasons)


def test_diff_theses_new_catalyst():
    from trade_thesis import diff_theses
    prev = {"stance": "flat", "conviction_0_to_10": 4,
            "invalidation_risks": [], "catalyst_watchlist": []}
    cur = {"stance": "flat", "conviction_0_to_10": 4,
           "invalidation_risks": [],
           "catalyst_watchlist": [{"event": "OPEC+ meeting", "date": "2026-05-01"}]}
    out = diff_theses(prev, cur)
    assert any("OPEC+" in d for d in out)


def test_diff_theses_prev_none():
    from trade_thesis import diff_theses
    assert diff_theses(None, {"stance": "flat"}) == []


def test_read_recent_theses_missing_file(tmp_path, monkeypatch):
    from trade_thesis import read_recent_theses
    # Point the audit path at a non-existent file
    import trade_thesis as tt
    monkeypatch.setattr(tt, "_AUDIT_PATH", tmp_path / "nonexistent.jsonl")
    assert read_recent_theses() == []


def test_read_recent_theses_happy_tail(tmp_path, monkeypatch):
    import trade_thesis as tt
    p = tmp_path / "theses.jsonl"
    rows = []
    for i in range(15):
        rows.append({
            "timestamp": f"2026-04-22T12:{i:02d}:00Z",
            "thesis": {"stance": "flat", "conviction_0_to_10": i, "thesis_summary": f"summary {i}"},
            "context": {}, "source": "rule-based", "model": None,
            "context_fingerprint": f"{i:016x}", "guardrails": [],
        })
    p.write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setattr(tt, "_AUDIT_PATH", p)
    out = tt.read_recent_theses(n=5)
    assert len(out) == 5
    assert out[0]["thesis"]["conviction_0_to_10"] == 14


def test_history_stats_with_mix():
    from trade_thesis import history_stats
    records = [
        {"thesis": {"stance": "long_spread", "conviction_0_to_10": 8}},
        {"thesis": {"stance": "short_spread", "conviction_0_to_10": 6}},
        {"thesis": {"stance": "flat", "conviction_0_to_10": 3}},
    ]
    s = history_stats(records)
    assert s["long"] == 1 and s["short"] == 1 and s["flat"] == 1
    assert s["avg_conf"] == pytest.approx(17/3)


# ---------------------------------------------------------------------------
# thesis_context.build_context — passes new kwargs through
# ---------------------------------------------------------------------------
def test_build_context_with_coint_and_crack(eia_fixture, synth_prices, spread_with_zscore, sample_backtest):
    from data_ingestion import fetch_inventory_data, fetch_ais_data
    from quantitative_models import categorize_flag_states, forecast_depletion
    from thesis_context import build_context

    inv_res = fetch_inventory_data()
    ais_res = fetch_ais_data(n_vessels=30)
    _, ais_agg = categorize_flag_states(ais_res.frame)
    dep = forecast_depletion(inv_res.frame, floor_bbls=300_000_000.0, lookback_weeks=4)
    pricing_res = SimpleNamespace(frame=synth_prices, source="yfinance", fetched_at=pd.Timestamp.utcnow())

    coint_info = {"verdict": "cointegrated", "p_value": 0.01, "hedge_ratio": 0.95, "half_life_days": 18.4}
    crack_info = {"ok": True, "latest_crack_usd": 28.5, "corr_30d_vs_brent_wti": 0.42}

    ctx = build_context(
        pricing_res=pricing_res,
        inventory_res=inv_res,
        spread_df=spread_with_zscore,
        backtest=sample_backtest,
        depletion=dep,
        ais_agg=ais_agg,
        ais_with_cat=categorize_flag_states(ais_res.frame)[0],
        z_threshold=2.0,
        floor_bbls=300_000_000.0,
        coint_info=coint_info,
        crack_info=crack_info,
    )
    assert ctx.coint_verdict == "cointegrated"
    assert ctx.coint_p_value == 0.01
    assert ctx.coint_hedge_ratio == 0.95
    assert ctx.coint_half_life_days == 18.4
    assert ctx.cushing_current_bbls is not None and ctx.cushing_current_bbls > 10e6
    assert ctx.crack_321_usd == 28.5
    assert ctx.crack_corr_30d == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# cointegration — graceful-on-failure
# ---------------------------------------------------------------------------
def test_crack_spread_missing_ticker(monkeypatch):
    import crack_spread as cs
    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    raw = pd.DataFrame({
        # No HO=F or CL=F — should surface "missing ticker" note
        "RB=F": np.linspace(2.5, 2.6, 30),
    }, index=idx)
    monkeypatch.setattr(cs, "_load", lambda tickers, years=1: raw)
    out = cs.compute_crack(brent_wti_daily=None)
    assert out.ok is False
    assert "missing" in out.note.lower() or "ticker" in out.note.lower()


def test_crack_spread_corr_guard_on_short_panel(monkeypatch):
    import crack_spread as cs
    idx = pd.date_range("2024-01-01", periods=150, freq="D")
    raw = pd.DataFrame({
        "RB=F": np.linspace(2.4, 2.7, 150),
        "HO=F": np.linspace(2.7, 3.0, 150),
        "CL=F": np.linspace(75.0, 82.0, 150),
    }, index=idx)
    monkeypatch.setattr(cs, "_load", lambda tickers, years=1: raw)
    # Short Brent-WTI panel (<32 rows) ⇒ corr stays NaN per the guard
    panel = pd.DataFrame({"Brent": [80, 81, 82], "WTI": [77, 78, 79]},
                         index=pd.date_range("2024-01-01", periods=3, freq="D"))
    out = cs.compute_crack(brent_wti_daily=panel)
    assert out.ok
    assert np.isnan(out.corr_30d_vs_brent_wti)


def test_eia_fetch_cushing_fixture(eia_fixture):
    from providers._eia import fetch_cushing
    s = fetch_cushing(start="2020-01-01")
    assert len(s) > 100
    # Cushing realistic range over 2020s
    assert 10e6 < float(s.iloc[-1]) < 100e6


def test_eia_fetch_inventory_missing_spr(eia_fixture, monkeypatch):
    """If SPR fetch blows up, Commercial + Cushing still populate the frame."""
    import providers._eia as eia

    original_fetch = eia._fetch_dnav
    def _patched(series: str, timeout: int = 15):
        if series == "WCSSTUS1":
            raise RuntimeError("SPR series down")
        return original_fetch(series, timeout)

    monkeypatch.setattr(eia, "_fetch_dnav", _patched)
    df = eia.fetch_inventory()
    assert not df.empty
    assert "Commercial_bbls" in df.columns
    assert "Cushing_bbls" in df.columns


def test_cointegration_bad_input_inconclusive(monkeypatch):
    from cointegration import engle_granger
    # Force the ADF path to raise
    import cointegration as ct

    def _boom(*a, **kw):
        raise RuntimeError("adf boom")

    if ct.adfuller is not None:
        monkeypatch.setattr(ct, "adfuller", _boom)
        idx = pd.date_range("2022-01-01", periods=200, freq="D")
        b = pd.Series(np.linspace(80, 82, 200), index=idx)
        w = pd.Series(np.linspace(77, 79, 200), index=idx)
        res = engle_granger(b, w)
        assert res.verdict == "inconclusive"
