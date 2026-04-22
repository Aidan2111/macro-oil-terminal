"""Unit tests for the quantitative_models module."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest


def test_spread_zscore_basic(synth_prices):
    from quantitative_models import compute_spread_zscore
    df = compute_spread_zscore(synth_prices, window=90)
    for col in ("Spread", "Z_Score"):
        assert col in df.columns
    assert df["Z_Score"].notna().sum() > 0
    assert np.isfinite(df["Z_Score"].dropna()).all()


def test_spread_zscore_empty():
    from quantitative_models import compute_spread_zscore
    df = compute_spread_zscore(pd.DataFrame(), window=90)
    assert df.empty or df.isna().all().all()


def test_forecast_depletion_basic(eia_fixture):
    from data_ingestion import fetch_inventory_data
    from quantitative_models import forecast_depletion
    inv = fetch_inventory_data().frame
    out = forecast_depletion(inv, floor_bbls=300_000_000.0, lookback_weeks=4)
    assert math.isfinite(out["daily_depletion_bbls"])
    assert 0.0 <= out["r_squared"] <= 1.0 + 1e-9


def test_forecast_depletion_rising():
    from quantitative_models import forecast_depletion
    idx = pd.date_range("2024-01-01", periods=52, freq="W-FRI")
    rising = pd.DataFrame(
        {"Total_Inventory_bbls": np.linspace(300e6, 900e6, 52)},
        index=idx,
    )
    out = forecast_depletion(rising, floor_bbls=300_000_000.0, lookback_weeks=4)
    assert out["projected_floor_date"] is None
    assert out["daily_depletion_bbls"] >= 0


def test_backtest_slippage_reduces_pnl(spread_with_zscore):
    from quantitative_models import backtest_zscore_meanreversion
    a = backtest_zscore_meanreversion(
        spread_with_zscore, entry_z=1.0, exit_z=0.2, slippage_per_bbl=0.0,
    )
    b = backtest_zscore_meanreversion(
        spread_with_zscore, entry_z=1.0, exit_z=0.2, slippage_per_bbl=0.5,
    )
    if a["n_trades"] > 0:
        assert b["total_pnl_usd"] <= a["total_pnl_usd"]


def test_backtest_commission_reduces_pnl(spread_with_zscore):
    from quantitative_models import backtest_zscore_meanreversion
    a = backtest_zscore_meanreversion(spread_with_zscore, entry_z=1.0, exit_z=0.2, commission_per_trade=0.0)
    b = backtest_zscore_meanreversion(spread_with_zscore, entry_z=1.0, exit_z=0.2, commission_per_trade=100.0)
    if a["n_trades"] > 0:
        assert b["total_pnl_usd"] < a["total_pnl_usd"]


def test_walk_forward_shape(spread_with_zscore):
    from quantitative_models import walk_forward_backtest
    wf = walk_forward_backtest(spread_with_zscore, entry_z=1.0, exit_z=0.2,
                               window_months=4, step_months=1)
    if not wf.empty:
        required = {"window_start", "window_end", "n_trades", "total_pnl_usd"}
        assert required.issubset(wf.columns)


def test_monte_carlo_percentiles_monotone(spread_with_zscore):
    from quantitative_models import monte_carlo_entry_noise
    mc = monte_carlo_entry_noise(spread_with_zscore, entry_z=1.0, exit_z=0.2, n_runs=40)
    assert mc["pnl_p05"] <= mc["pnl_p95"]
    assert mc["n_runs"] == 40


def test_regime_breakdown_both_buckets(spread_with_zscore, sample_backtest):
    from quantitative_models import regime_breakdown
    if sample_backtest["n_trades"] > 0:
        rb = regime_breakdown(spread_with_zscore, sample_backtest["trades"])
        assert set(rb["regime"]) == {"low_vol", "high_vol"}


def test_categorize_flag_states():
    from data_ingestion import fetch_ais_data
    from quantitative_models import categorize_flag_states
    det, agg = categorize_flag_states(fetch_ais_data(50).frame)
    assert {"Jones Act / Domestic", "Shadow Risk", "Sanctioned"}.issubset(set(agg["Category"]))
    assert (agg["Total_Cargo_Mbbl"] >= 0).all()
