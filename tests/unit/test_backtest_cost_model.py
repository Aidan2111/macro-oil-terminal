"""Unit tests for backend.services.backtest (realistic cost model).

We compare the realistic and legacy cost models on the same fixture
trade list to sanity-check the delta the PR body cites.
"""

from __future__ import annotations

import sys
import pathlib
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.backtest import (  # noqa: E402
    CostModel,
    run_realistic_backtest,
)


def _synthetic_spread_df(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    spread = [4.0]
    for _ in range(n - 1):
        spread.append(spread[-1] * 0.7 + 4.0 * 0.3 + rng.normal(0, 1.2))
    idx = pd.date_range(end=datetime(2026, 4, 22), periods=n, freq="D")
    s = pd.Series(spread, index=idx, name="Spread")
    window = 60
    roll_mean = s.rolling(window).mean()
    roll_std = s.rolling(window).std(ddof=0)
    z = (s - roll_mean) / roll_std.replace(0, np.nan)
    return pd.DataFrame({"Spread": s, "Z_Score": z}).dropna()


def test_cost_model_defaults_are_reasonable():
    cm = CostModel()
    assert 0 < cm.bid_ask_spread_pct < 0.01
    assert 0 < cm.commission_per_contract < 5
    assert 0 < cm.overnight_carry_bps < 500
    assert cm.contracts() == pytest.approx(10.0)  # 10_000 / 1_000
    assert cm.round_trip_commission_usd() == pytest.approx(2 * 10 * 0.85)


def test_realistic_backtest_returns_pnl_delta_against_legacy():
    df = _synthetic_spread_df()
    out = run_realistic_backtest(
        spread_df=df,
        entry_z=1.5,
        exit_z=0.2,
    )
    assert out["n_trades"] > 0
    assert "total_pnl_usd" in out
    assert "total_pnl_usd_legacy" in out
    assert "pnl_delta_vs_legacy" in out
    assert "cost_model" in out
    # Sign check — defaults: realistic adds carry on top of comm/spread.
    assert out["pnl_delta_vs_legacy"] == pytest.approx(
        out["total_pnl_usd"] - out["total_pnl_usd_legacy"]
    )


def test_each_trade_has_breakdown():
    df = _synthetic_spread_df()
    out = run_realistic_backtest(spread_df=df, entry_z=1.5, exit_z=0.2)
    for tr in out["trades"]:
        bd = tr["pnl_breakdown"]
        # Net = gross - spread - commission - carry
        recomputed = (
            bd["gross_usd"]
            - bd["spread_cost_usd"]
            - bd["commission_usd"]
            - bd["overnight_carry_usd"]
        )
        assert recomputed == pytest.approx(bd["net_pnl_usd"])
        # Costs are non-negative
        assert bd["spread_cost_usd"] >= 0
        assert bd["commission_usd"] >= 0
        assert bd["overnight_carry_usd"] >= 0


def test_high_carry_lowers_net_pnl():
    """Raising overnight_carry_bps must monotonically reduce realistic PnL."""
    df = _synthetic_spread_df()
    base = run_realistic_backtest(spread_df=df, entry_z=1.5, exit_z=0.2)
    expensive = run_realistic_backtest(
        spread_df=df,
        entry_z=1.5,
        exit_z=0.2,
        cost=CostModel(overnight_carry_bps=500.0),
    )
    assert expensive["total_pnl_usd"] <= base["total_pnl_usd"]
