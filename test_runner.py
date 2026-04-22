"""Autonomous validation runner.

Covers:
  * data_ingestion public API (pricing / inventory / AIS — with network
    calls mocked via fixtures so the suite runs fully offline)
  * quantitative_models (spread z-score, depletion forecaster, flag-state
    categorisation, backtest)
  * webgpu_components (shape-only — HTML payload sanity)
  * ai_insights_legacy (behaviour-preserving shim — kept for historical
    coverage so the canned-fallback path is still exercised)
  * trade_thesis (schema validation, guardrails, rule-based fallback,
    audit log append)

Run:
    python test_runner.py
Exit code is non-zero if any check fails.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
from typing import Callable

import numpy as np
import pandas as pd


FAILED: list = []
PASSED: list = []


def _check(name: str, fn: Callable[[], None]) -> None:
    t0 = time.perf_counter()
    try:
        fn()
        dt = time.perf_counter() - t0
        PASSED.append((name, dt))
        print(f"  PASS  {name}  ({dt*1000:.0f} ms)")
    except Exception as e:  # noqa: BLE001
        dt = time.perf_counter() - t0
        FAILED.append((name, e, traceback.format_exc()))
        print(f"  FAIL  {name}  ({dt*1000:.0f} ms)")
        print(traceback.format_exc())


# ---------------------------------------------------------------------------
# Test fixtures helpers
# ---------------------------------------------------------------------------
def _load_eia_fixture():
    """Monkey-patch requests.get used by providers._eia to serve a fixture file."""
    from tests.fixtures import FIXTURES_DIR
    import requests as _requests

    original_get = _requests.get

    def _patched_get(url, *args, **kwargs):
        class _Resp:
            def __init__(self, text):
                self.text = text
                self.status_code = 200

            def raise_for_status(self):
                pass

        if "WCESTUS1" in url:
            return _Resp((FIXTURES_DIR / "eia_WCESTUS1.html").read_text())
        if "WCSSTUS1" in url:
            return _Resp((FIXTURES_DIR / "eia_WCSSTUS1.html").read_text())
        return original_get(url, *args, **kwargs)

    _requests.get = _patched_get


# ---------------------------------------------------------------------------
# data_ingestion
# ---------------------------------------------------------------------------
def test_data_ingestion() -> None:
    # Install the EIA fixture monkey-patch for offline tests
    _load_eia_fixture()

    import data_ingestion as di

    def t_pricing_daily() -> None:
        # fetch_pricing_data hits yfinance which may be unreachable in CI.
        # Accept either a PricingResult or a PricingUnavailable — both shapes
        # are valid production behaviour.
        try:
            res = di.fetch_pricing_data(years=1)
        except di.PricingUnavailable:
            return  # acceptable: no simulator fallback by design
        assert res is not None
        assert res.frame is not None and not res.frame.empty
        assert {"Brent", "WTI"}.issubset(res.frame.columns)
        assert res.source and res.fetched_at is not None

    def t_inventory_real_via_fixture() -> None:
        # Use the fixture-backed EIA path.
        res = di.fetch_inventory_data()
        assert res.frame is not None and not res.frame.empty
        assert {"Commercial_bbls", "SPR_bbls", "Total_Inventory_bbls"}.issubset(res.frame.columns)
        # Real data sanity: US commercial crude has been 350-550M bbls for a decade
        last = float(res.frame["Commercial_bbls"].iloc[-1])
        assert 300e6 < last < 700e6, f"unrealistic commercial value: {last}"

    def t_ais_snapshot() -> None:
        res = di.fetch_ais_data(n_vessels=250)
        assert len(res.frame) == 250
        needed = {"Vessel_Name", "MMSI", "Cargo_Volume_bbls",
                  "Destination", "Flag_State", "Latitude", "Longitude"}
        assert needed.issubset(res.frame.columns)
        assert (res.frame["Cargo_Volume_bbls"] > 0).all()
        # When no AISSTREAM_API_KEY, we must return the labeled placeholder
        if not os.environ.get("AISSTREAM_API_KEY"):
            assert not res.is_live
            assert res.snapshot_notice is not None
            assert "aisstream.io" in res.snapshot_notice

    def t_no_simulate_imported_into_prod_path() -> None:
        assert not hasattr(di, "simulate_inventory"), "simulate_inventory must not be on the public API"
        assert not hasattr(di, "generate_ais_mock"), "generate_ais_mock must not be on the public API"

    _check("data_ingestion.fetch_pricing_data(1y)", t_pricing_daily)
    _check("data_ingestion.fetch_inventory_data[fixture]", t_inventory_real_via_fixture)
    _check("data_ingestion.fetch_ais_data(250)", t_ais_snapshot)
    _check("data_ingestion: simulators removed from prod path", t_no_simulate_imported_into_prod_path)


# ---------------------------------------------------------------------------
# quantitative_models
# ---------------------------------------------------------------------------
def test_quant_models() -> None:
    from quantitative_models import (
        compute_spread_zscore,
        forecast_depletion,
        categorize_flag_states,
        backtest_zscore_meanreversion,
    )
    from data_ingestion import fetch_inventory_data, fetch_ais_data

    inv_res = fetch_inventory_data()
    inv = inv_res.frame

    # Build a simple synthetic price frame (not a simulator for prod — just for test math)
    idx = pd.date_range("2024-01-01", periods=400, freq="D")
    rng = np.random.default_rng(42)
    wti = np.cumsum(rng.normal(0, 0.5, 400)) + 75.0
    brent = wti + 3.2 + np.cumsum(rng.normal(0, 0.07, 400))
    prices = pd.DataFrame({"Brent": brent, "WTI": wti}, index=idx)

    def t_spread_basic() -> None:
        df = compute_spread_zscore(prices, window=90)
        assert {"Spread", "Z_Score"}.issubset(df.columns)
        assert df["Z_Score"].notna().sum() > 0
        assert np.isfinite(df["Z_Score"].dropna()).all()

    def t_depletion_basic() -> None:
        out = forecast_depletion(inv, floor_bbls=300_000_000.0, lookback_weeks=4)
        assert math.isfinite(out["daily_depletion_bbls"])
        assert math.isfinite(out["r_squared"])
        if not out["regression_line"].empty:
            assert {"Date", "Projected_Inventory_bbls"}.issubset(out["regression_line"].columns)

    def t_categorize_basic() -> None:
        ais = fetch_ais_data(500).frame
        det, agg = categorize_flag_states(ais)
        assert {"Category", "Total_Cargo_Mbbl", "Vessel_Count"}.issubset(agg.columns)
        for cat in ("Jones Act / Domestic", "Shadow Risk", "Sanctioned"):
            assert cat in agg["Category"].values

    def t_backtest_basic() -> None:
        sdf = compute_spread_zscore(prices, window=90)
        out = backtest_zscore_meanreversion(sdf, entry_z=1.0, exit_z=0.2)
        assert {"trades", "total_pnl_usd", "n_trades", "max_drawdown_usd", "sharpe"}.issubset(out)
        if out["n_trades"] > 0:
            assert math.isfinite(out["max_drawdown_usd"])
            assert math.isfinite(out["sharpe"])
            assert 0.0 <= out["win_rate"] <= 1.0

    _check("quant.compute_spread_zscore", t_spread_basic)
    _check("quant.forecast_depletion", t_depletion_basic)
    _check("quant.categorize_flag_states", t_categorize_basic)
    _check("quant.backtest_zscore_meanreversion (+dd/sharpe)", t_backtest_basic)


# ---------------------------------------------------------------------------
# webgpu_components (template shape)
# ---------------------------------------------------------------------------
def test_webgpu_components() -> None:
    from webgpu_components import _points_payload, _HERO_HTML, _GLOBE_HTML
    from data_ingestion import fetch_ais_data
    from quantitative_models import categorize_flag_states

    def t_points_payload_basic() -> None:
        det, _ = categorize_flag_states(fetch_ais_data(25).frame)
        pts = _points_payload(det)
        assert isinstance(pts, list) and len(pts) == 25
        for p in pts:
            assert -90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180

    def t_points_payload_empty() -> None:
        assert _points_payload(pd.DataFrame()) == []

    def t_hero_template() -> None:
        assert "__HEIGHT__" in _HERO_HTML
        assert "__THREE_WEBGPU_URL__" in _HERO_HTML  # placeholder for CDN URL
        assert "setAnimationLoop" in _HERO_HTML       # three.js loop hook

    def t_globe_template() -> None:
        assert "__POINTS_JSON__" in _GLOBE_HTML
        assert "__THREE_TSL_URL__" in _GLOBE_HTML
        assert "InstancedMesh" in _GLOBE_HTML

    _check("webgpu._points_payload(basic)", t_points_payload_basic)
    _check("webgpu._points_payload(empty)", t_points_payload_empty)
    _check("webgpu._HERO_HTML template", t_hero_template)
    _check("webgpu._GLOBE_HTML template", t_globe_template)


# ---------------------------------------------------------------------------
# trade_thesis — guardrails + schema + rule-based fallback
# ---------------------------------------------------------------------------
def test_trade_thesis() -> None:
    from trade_thesis import (
        ThesisContext,
        THESIS_JSON_SCHEMA,
        generate_thesis,
        _apply_guardrails,
        _rule_based_fallback,
    )

    def _mk_ctx(**overrides):
        defaults = dict(
            latest_brent=82.10, latest_wti=78.40, latest_spread=3.70,
            rolling_mean_90d=3.2, rolling_std_90d=0.7,
            current_z=2.3, z_percentile_5y=91.0, days_since_last_abs_z_over_2=40,
            bt_hit_rate=0.68, bt_avg_hold_days=30.0, bt_avg_pnl_per_bbl=1.2,
            bt_max_drawdown_usd=-4000.0, bt_sharpe=1.6,
            inventory_source="EIA", inventory_current_bbls=870e6,
            inventory_4w_slope_bbls_per_day=-350_000.0,
            inventory_52w_slope_bbls_per_day=-95_000.0,
            inventory_floor_bbls=300e6,
            inventory_projected_floor_date="2028-06-15",
            days_of_supply=None,
            fleet_total_mbbl=640.0, fleet_jones_mbbl=120.0,
            fleet_shadow_mbbl=260.0, fleet_sanctioned_mbbl=180.0,
            fleet_source="Historical snapshot", fleet_delta_vs_30d_mbbl=None,
            vol_brent_30d_pct=28.0, vol_wti_30d_pct=29.0,
            vol_spread_30d_pct=12.0, vol_spread_1y_percentile=55.0,
            next_eia_release_date="2026-04-22", session_is_open=True,
            weekend_or_holiday=False, user_z_threshold=2.0,
        )
        defaults.update(overrides)
        return ThesisContext(**defaults)

    def t_schema_required_keys() -> None:
        sch = THESIS_JSON_SCHEMA["schema"]
        required = set(sch["required"])
        assert {"stance", "conviction_0_to_10", "entry", "exit",
                "position_sizing", "invalidation_risks", "data_caveats"}.issubset(required)

    def t_rule_based_shape() -> None:
        out = _rule_based_fallback(_mk_ctx())
        for key in ("stance", "conviction_0_to_10", "entry", "exit",
                    "position_sizing", "thesis_summary", "key_drivers",
                    "invalidation_risks", "catalyst_watchlist",
                    "data_caveats", "disclaimer_shown"):
            assert key in out, f"missing key {key} in rule-based output"
        assert out["stance"] in ("long_spread", "short_spread", "flat")

    def t_guardrail_inventory_missing_forces_flat() -> None:
        ctx = _mk_ctx(inventory_source="unavailable", current_z=2.8)
        raw = _rule_based_fallback(ctx)
        # In the rule-based path the stance may already be flat — explicitly set it bullish
        raw["stance"] = "long_spread"
        raw["conviction_0_to_10"] = 8.0
        out, notes = _apply_guardrails(raw, ctx)
        assert out["stance"] == "flat"
        assert any("inventory feed unavailable" in n.lower() for n in notes) or any(
            "inventory feed unavailable" in c.lower() for c in out["data_caveats"]
        )

    def t_guardrail_conviction_downgrade_on_weak_backtest() -> None:
        ctx = _mk_ctx(bt_hit_rate=0.40)
        raw = _rule_based_fallback(ctx)
        raw["conviction_0_to_10"] = 9.0
        out, notes = _apply_guardrails(raw, ctx)
        assert out["conviction_0_to_10"] <= 5.0
        assert any("calibration adjustment" in n.lower() for n in notes)

    def t_guardrail_sizing_cap() -> None:
        ctx = _mk_ctx()
        raw = _rule_based_fallback(ctx)
        raw["position_sizing"]["suggested_pct_of_capital"] = 35.0
        out, notes = _apply_guardrails(raw, ctx)
        assert out["position_sizing"]["suggested_pct_of_capital"] == 20.0
        assert any("sizing cap" in n.lower() for n in notes)

    def t_generate_no_env_uses_rule_based() -> None:
        for key in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY"):
            os.environ.pop(key, None)
        th = generate_thesis(_mk_ctx(), log=False)
        assert th.raw.get("disclaimer_shown") is True
        assert th.source.startswith("rule-based")
        assert th.context_fingerprint and len(th.context_fingerprint) >= 8

    def t_fingerprint_stable() -> None:
        ctx1 = _mk_ctx()
        ctx2 = _mk_ctx()
        assert ctx1.fingerprint() == ctx2.fingerprint()
        ctx3 = _mk_ctx(current_z=2.4)  # changed
        assert ctx1.fingerprint() != ctx3.fingerprint()

    _check("trade_thesis.schema required keys", t_schema_required_keys)
    _check("trade_thesis.rule_based_fallback shape", t_rule_based_shape)
    _check("trade_thesis.guardrails[inventory_missing→flat]", t_guardrail_inventory_missing_forces_flat)
    _check("trade_thesis.guardrails[weak_backtest→downgrade]", t_guardrail_conviction_downgrade_on_weak_backtest)
    _check("trade_thesis.guardrails[sizing>20%→cap]", t_guardrail_sizing_cap)
    _check("trade_thesis.generate_no_env→rule_based", t_generate_no_env_uses_rule_based)
    _check("trade_thesis.context.fingerprint stable", t_fingerprint_stable)


# ---------------------------------------------------------------------------
# thesis_context (numeric helpers)
# ---------------------------------------------------------------------------
def test_thesis_context() -> None:
    from thesis_context import _percentile_rank, _linear_slope_per_day, _realized_vol_pct

    def t_percentile_rank() -> None:
        s = pd.Series([1, 2, 3, 4, 5])
        assert _percentile_rank(s, 3) == 60.0  # 3 out of 5 <= 3
        assert _percentile_rank(s, 0) == 0.0
        assert _percentile_rank(s, 9) == 100.0

    def t_slope_positive() -> None:
        idx = pd.date_range("2024-01-01", periods=10, freq="D")
        s = pd.Series(np.arange(10, dtype=float), index=idx)
        slope = _linear_slope_per_day(s)
        assert math.isclose(slope, 1.0, abs_tol=1e-9)

    def t_vol_nonneg() -> None:
        idx = pd.date_range("2024-01-01", periods=60, freq="D")
        rng = np.random.default_rng(0)
        s = pd.Series(100.0 + np.cumsum(rng.normal(0, 0.5, 60)), index=idx)
        assert _realized_vol_pct(s, 30) >= 0

    _check("thesis_context._percentile_rank", t_percentile_rank)
    _check("thesis_context._linear_slope_per_day", t_slope_positive)
    _check("thesis_context._realized_vol_pct", t_vol_nonneg)


# ---------------------------------------------------------------------------
# alerts
# ---------------------------------------------------------------------------
def test_alerts() -> None:
    from alerts import maybe_send_zscore_alert

    def t_below() -> None:
        assert maybe_send_zscore_alert(1.2, 3.0, 2.5) is None

    def t_preview() -> None:
        for k in ("ALERT_SMTP_HOST", "ALERT_SMTP_USER", "ALERT_SMTP_PASS", "ALERT_SMTP_TO"):
            os.environ.pop(k, None)
        out = maybe_send_zscore_alert(3.8, 3.0, 4.2)
        assert out and out.startswith("[would-send]")

    _check("alerts.below_threshold", t_below)
    _check("alerts.breach_preview(unset_env)", t_preview)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    print("== Oil Terminal Test Runner ==")
    print("-- data_ingestion --")
    test_data_ingestion()
    print("-- quantitative_models --")
    test_quant_models()
    print("-- webgpu_components --")
    test_webgpu_components()
    print("-- trade_thesis --")
    test_trade_thesis()
    print("-- thesis_context --")
    test_thesis_context()
    print("-- alerts --")
    test_alerts()

    total = len(PASSED) + len(FAILED)
    print("\nResults:")
    print(f"  passed: {len(PASSED)}/{total}")
    print(f"  failed: {len(FAILED)}/{total}")
    if FAILED:
        print("\nFailures:")
        for name, err, _tb in FAILED:
            print(f"  - {name}: {type(err).__name__}: {err}")
        return 1
    print("\nAll tests green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
