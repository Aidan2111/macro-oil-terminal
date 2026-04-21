"""Autonomous validation runner.

Exercises every public helper in :mod:`data_ingestion` and
:mod:`quantitative_models`. Guards against:
  * NoneType dereferences
  * Dimension mismatches in downstream math
  * Obvious infinite loops (each test is wrapped in a soft 60s timeout
    via a subprocess-friendly design; here we just time each function)
  * Regression outputs that would crash the Streamlit layer

Run:
    python test_runner.py
Exit code is non-zero if any check fails.
"""

from __future__ import annotations

import math
import sys
import time
import traceback
from typing import Callable, Tuple

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
# data_ingestion
# ---------------------------------------------------------------------------
def test_data_ingestion() -> None:
    from data_ingestion import fetch_pricing_data, simulate_inventory, generate_ais_mock

    def t_pricing() -> None:
        df = fetch_pricing_data(years=5)
        assert df is not None, "fetch_pricing_data returned None"
        assert isinstance(df, pd.DataFrame)
        assert not df.empty, "pricing frame is empty"
        assert {"Brent", "WTI"}.issubset(df.columns)
        assert df.index.is_monotonic_increasing
        assert df[["Brent", "WTI"]].isna().any().any() is np.False_ or df[["Brent", "WTI"]].notna().all().all()
        assert (df["Brent"] > 0).all() and (df["WTI"] > 0).all()
        assert len(df) >= 365, f"pricing too short: {len(df)}"

    def t_pricing_shortwindow() -> None:
        df = fetch_pricing_data(years=1)
        assert not df.empty and {"Brent", "WTI"}.issubset(df.columns)

    def t_inventory() -> None:
        df = simulate_inventory(years=2)
        assert df is not None and not df.empty
        assert "Total_Inventory_bbls" in df.columns
        assert len(df) >= 8
        assert df["Total_Inventory_bbls"].notna().all()
        # Ensure trend is net downward over the window
        first = df["Total_Inventory_bbls"].iloc[: max(1, len(df)//10)].mean()
        last = df["Total_Inventory_bbls"].iloc[-max(1, len(df)//10):].mean()
        assert last < first, "expected net drawdown over simulated window"

    def t_inventory_short() -> None:
        df = simulate_inventory(years=0)  # clamps to 8 weeks minimum
        assert not df.empty

    def t_ais() -> None:
        df = generate_ais_mock(n_vessels=500)
        assert df is not None and len(df) == 500
        expected = {
            "Vessel_Name", "MMSI", "Cargo_Volume_bbls",
            "Destination", "Flag_State", "Latitude", "Longitude",
        }
        assert expected.issubset(set(df.columns)), f"AIS missing cols: {expected - set(df.columns)}"
        assert (df["Cargo_Volume_bbls"] > 0).all()
        assert df["Latitude"].between(-90, 90).all()
        assert df["Longitude"].between(-180, 180).all()
        # Favored flags should actually dominate
        favored = {"Panama", "Liberia", "United States", "Iran", "Russia"}
        assert df["Flag_State"].isin(favored).mean() > 0.5, "expected favored flags to dominate"

    def t_ais_small() -> None:
        df = generate_ais_mock(n_vessels=5)
        assert len(df) == 5

    _check("data_ingestion.fetch_pricing_data(5y)", t_pricing)
    _check("data_ingestion.fetch_pricing_data(1y)", t_pricing_shortwindow)
    _check("data_ingestion.simulate_inventory(2y)", t_inventory)
    _check("data_ingestion.simulate_inventory(tiny)", t_inventory_short)
    _check("data_ingestion.generate_ais_mock(500)", t_ais)
    _check("data_ingestion.generate_ais_mock(5)", t_ais_small)


# ---------------------------------------------------------------------------
# quantitative_models
# ---------------------------------------------------------------------------
def test_quant_models() -> None:
    from data_ingestion import fetch_pricing_data, simulate_inventory, generate_ais_mock
    from quantitative_models import (
        compute_spread_zscore,
        forecast_depletion,
        categorize_flag_states,
    )

    prices = fetch_pricing_data(years=5)
    inv = simulate_inventory(years=2)
    ais = generate_ais_mock(n_vessels=500)

    def t_spread_basic() -> None:
        df = compute_spread_zscore(prices, window=90)
        assert {"Brent", "WTI", "Spread", "Z_Score"}.issubset(df.columns)
        assert len(df) == len(prices)
        # Z-score should have finite values somewhere after warm-up
        assert df["Z_Score"].notna().sum() > 0
        assert np.isfinite(df["Z_Score"].dropna()).all()

    def t_spread_empty() -> None:
        df = compute_spread_zscore(pd.DataFrame(), window=90)
        assert df.empty or df.isna().all().all()

    def t_spread_small_window() -> None:
        df = compute_spread_zscore(prices, window=10)
        assert df["Z_Score"].notna().sum() > 0

    def t_depletion_basic() -> None:
        out = forecast_depletion(inv, floor_bbls=300_000_000.0, lookback_weeks=4)
        assert isinstance(out, dict)
        assert set(out.keys()) >= {
            "daily_depletion_bbls", "weekly_depletion_bbls",
            "projected_floor_date", "regression_line",
            "r_squared", "current_inventory", "floor_bbls",
        }
        assert math.isfinite(out["daily_depletion_bbls"])
        assert math.isfinite(out["weekly_depletion_bbls"])
        assert math.isfinite(out["r_squared"])
        assert out["regression_line"] is not None
        if not out["regression_line"].empty:
            assert {"Date", "Projected_Inventory_bbls"}.issubset(out["regression_line"].columns)

    def t_depletion_weekspan() -> None:
        for weeks in (2, 4, 12, 26):
            out = forecast_depletion(inv, floor_bbls=300_000_000.0, lookback_weeks=weeks)
            assert math.isfinite(out["daily_depletion_bbls"])

    def t_depletion_empty() -> None:
        out = forecast_depletion(pd.DataFrame(), floor_bbls=300_000_000.0, lookback_weeks=4)
        assert out["projected_floor_date"] is None
        assert out["regression_line"].empty

    def t_depletion_rising() -> None:
        # If inventory is rising, projected floor date should be None (no breach)
        rising = inv.copy()
        rising["Total_Inventory_bbls"] = np.linspace(300e6, 900e6, len(rising))
        out = forecast_depletion(rising, floor_bbls=300_000_000.0, lookback_weeks=4)
        assert out["projected_floor_date"] is None
        assert out["daily_depletion_bbls"] >= 0

    def t_categorize_basic() -> None:
        det, agg = categorize_flag_states(ais)
        assert "Category" in det.columns
        assert {"Category", "Total_Cargo_Mbbl", "Vessel_Count"}.issubset(agg.columns)
        for cat in ("Jones Act / Domestic", "Shadow Risk", "Sanctioned"):
            assert cat in agg["Category"].values, f"missing headline category {cat}"
        # Total conservation: sum of categorized cargo == total
        assert abs(det["Cargo_Volume_bbls"].sum() - ais["Cargo_Volume_bbls"].sum()) < 1e-6

    def t_categorize_edges() -> None:
        det, agg = categorize_flag_states(pd.DataFrame())
        assert not agg.empty
        assert (agg["Total_Cargo_Mbbl"] == 0).all()

    def t_spread_deterministic() -> None:
        # Feed a known synthetic frame, verify spread math
        idx = pd.date_range("2024-01-01", periods=120, freq="D")
        df = pd.DataFrame({"Brent": np.linspace(70, 90, 120), "WTI": np.linspace(68, 85, 120)}, index=idx)
        out = compute_spread_zscore(df, window=30)
        assert np.allclose(out["Spread"], out["Brent"] - out["WTI"])
        # At end of window Z should be finite
        assert math.isfinite(out["Z_Score"].iloc[-1])

    _check("quant.compute_spread_zscore(basic)", t_spread_basic)
    _check("quant.compute_spread_zscore(empty)", t_spread_empty)
    _check("quant.compute_spread_zscore(small_window)", t_spread_small_window)
    _check("quant.compute_spread_zscore(deterministic)", t_spread_deterministic)
    _check("quant.forecast_depletion(basic)", t_depletion_basic)
    _check("quant.forecast_depletion(weeks)", t_depletion_weekspan)
    _check("quant.forecast_depletion(empty)", t_depletion_empty)
    _check("quant.forecast_depletion(rising)", t_depletion_rising)
    _check("quant.categorize_flag_states(basic)", t_categorize_basic)
    _check("quant.categorize_flag_states(edges)", t_categorize_edges)


# ---------------------------------------------------------------------------
# webgpu_components (string/shape only — no rendering under test)
# ---------------------------------------------------------------------------
def test_webgpu_components() -> None:
    from webgpu_components import _points_payload, _HERO_HTML, _GLOBE_HTML
    from data_ingestion import generate_ais_mock
    from quantitative_models import categorize_flag_states

    def t_points_payload() -> None:
        det, _ = categorize_flag_states(generate_ais_mock(n_vessels=25))
        pts = _points_payload(det)
        assert isinstance(pts, list) and len(pts) == 25
        for p in pts:
            assert {"lat", "lon", "color", "cargo", "name", "flag", "category"}.issubset(p.keys())
            assert -90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180

    def t_points_payload_empty() -> None:
        pts = _points_payload(pd.DataFrame())
        assert pts == []

    def t_hero_html_template() -> None:
        assert "__HEIGHT__" in _HERO_HTML  # placeholder should still exist pre-render

    def t_globe_html_template() -> None:
        assert "__HEIGHT__" in _GLOBE_HTML and "__POINTS_JSON__" in _GLOBE_HTML

    _check("webgpu._points_payload(basic)", t_points_payload)
    _check("webgpu._points_payload(empty)", t_points_payload_empty)
    _check("webgpu._HERO_HTML template", t_hero_html_template)
    _check("webgpu._GLOBE_HTML template", t_globe_html_template)


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

    total = len(PASSED) + len(FAILED)
    print("\nResults:")
    print(f"  passed: {len(PASSED)}/{total}")
    print(f"  failed: {len(FAILED)}/{total}")
    if FAILED:
        print("\nFailures:")
        for name, err, tb in FAILED:
            print(f"  - {name}: {type(err).__name__}: {err}")
        return 1
    print("\nAll tests green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
