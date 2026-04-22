"""Full build_context() coverage using fixture-backed real inventory."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd


def test_build_context_end_to_end(eia_fixture, synth_prices, spread_with_zscore, sample_backtest):
    from data_ingestion import fetch_inventory_data, fetch_ais_data
    from quantitative_models import categorize_flag_states, forecast_depletion
    from thesis_context import build_context

    inv_res = fetch_inventory_data()
    ais_res = fetch_ais_data(n_vessels=50)
    _, ais_agg = categorize_flag_states(ais_res.frame)
    dep = forecast_depletion(inv_res.frame, floor_bbls=300_000_000.0, lookback_weeks=4)

    pricing_res = SimpleNamespace(frame=synth_prices, source="yfinance", fetched_at=pd.Timestamp.utcnow())

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
    )

    # Spot-check: every numeric field finite, calendar-ish fields populated
    assert np.isfinite(ctx.latest_brent)
    assert np.isfinite(ctx.current_z)
    assert ctx.inventory_source == "EIA"
    assert ctx.inventory_current_bbls > 0
    assert ctx.vol_brent_30d_pct >= 0
    assert 0 <= ctx.vol_spread_1y_percentile <= 100
    assert ctx.next_eia_release_date
    assert ctx.user_z_threshold == 2.0
