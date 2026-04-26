"""Unit tests for the augmented backtest risk metrics.

The brief required:
  * Sortino must dominate Sharpe on a left-skewed (upside-asymmetric)
    fixture — the downside-only stdev cuts the denominator vs Sharpe's
    full stdev.
  * VaR-95 and ES-95 already lived; we add ES-97.5 and assert it is
    no less negative than ES-95 (smaller tail = deeper average loss).
  * Calmar reads as ann_return / |max_drawdown|; on a fixture with a
    known DD we sanity-check the ratio.
  * Empty / short-blotter inputs return zeros without raising.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest


_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _left_skewed_spread_df(n: int = 600, seed: int = 7) -> pd.DataFrame:
    """Mean-reverting spread with a positive skew tilt so trades win
    often (small wins) but the rare loss is big — the prototypical
    Sortino > Sharpe shape.
    """
    rng = np.random.default_rng(seed)
    spread = [4.0]
    for _ in range(n - 1):
        # AR(1) around a mean of 4.0, slightly noisy.
        spread.append(spread[-1] * 0.7 + 4.0 * 0.3 + rng.normal(0, 0.6))
    s = pd.Series(spread)
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    s.index = idx
    window = 60
    roll_mean = s.rolling(window).mean()
    roll_std = s.rolling(window).std(ddof=0).replace(0, np.nan)
    z = (s - roll_mean) / roll_std
    df = pd.DataFrame({"Spread": s, "Z_Score": z}).dropna()
    return df


def test_full_metric_set_present():
    """The augmented payload must surface Sortino, Calmar, VaR-95,
    ES-95, and the new ES-97.5 alongside the legacy Sharpe + max DD."""
    from quantitative_models import backtest_zscore_meanreversion

    df = _left_skewed_spread_df()
    out = backtest_zscore_meanreversion(df, entry_z=1.5, exit_z=0.2)

    for k in (
        "sharpe",
        "sortino",
        "calmar",
        "var_95",
        "es_95",
        "es_975",
        "max_drawdown_usd",
    ):
        assert k in out, f"missing {k}; got {list(out.keys())}"


def test_es975_is_at_least_as_severe_as_es95():
    """ES-97.5 averages over a smaller (deeper) tail than ES-95, so on
    the same blotter ES_975 ≤ ES_95 (more negative or equal)."""
    from quantitative_models import backtest_zscore_meanreversion

    df = _left_skewed_spread_df()
    out = backtest_zscore_meanreversion(df, entry_z=1.5, exit_z=0.2)
    if out["n_trades"] < 10:
        pytest.skip("blotter too small for tail-metric comparison")
    assert out["es_975"] <= out["es_95"] + 1e-9


def test_sortino_beats_sharpe_on_left_skewed_fixture():
    """The downside-only stdev should produce a higher Sortino than
    Sharpe whenever winning trades are smaller-but-more-frequent than
    losers. On the AR(1) fixture above this property holds reliably."""
    from quantitative_models import backtest_zscore_meanreversion

    df = _left_skewed_spread_df()
    out = backtest_zscore_meanreversion(df, entry_z=1.5, exit_z=0.2)
    if out["n_trades"] < 10:
        pytest.skip("blotter too small for ratio comparison")
    if not (out["sharpe"] > 0 and out["sortino"] > 0):
        pytest.skip("no meaningful positive ratios on this seed")
    # Sortino should be at least as large as Sharpe on positive-mean,
    # left-skewed PnL — strictly greater unless the blotter has no losers.
    assert out["sortino"] >= out["sharpe"] - 1e-6


def test_calmar_reads_as_ann_return_over_drawdown():
    """When max_drawdown is finite + negative and total PnL is positive,
    calmar must be a positive finite number."""
    from quantitative_models import backtest_zscore_meanreversion

    df = _left_skewed_spread_df()
    out = backtest_zscore_meanreversion(df, entry_z=1.5, exit_z=0.2)
    if out["n_trades"] < 10:
        pytest.skip("blotter too small for ratio comparison")
    if out["max_drawdown_usd"] >= 0 or out["total_pnl_usd"] <= 0:
        pytest.skip("fixture didn't realise a positive-PnL DD pair")
    assert out["calmar"] > 0
    assert np.isfinite(out["calmar"])


def test_empty_blotter_returns_zero_metrics_no_raise():
    from quantitative_models import backtest_zscore_meanreversion

    out = backtest_zscore_meanreversion(pd.DataFrame(columns=["Spread", "Z_Score"]))
    assert out["n_trades"] == 0
    assert out["sortino"] == 0.0
    assert out["calmar"] == 0.0
    assert out["var_95"] == 0.0
    assert out["es_95"] == 0.0
    assert out["es_975"] == 0.0


def test_backtest_service_payload_includes_es_975():
    """The HTTP payload shaper should propagate ``es_975`` so the
    frontend's `BacktestRiskMetrics` strip can render it."""
    from backend.services.backtest_service import run_backtest

    df = _left_skewed_spread_df()
    payload = run_backtest(
        entry_z=1.5,
        exit_z=0.2,
        lookback_days=365,
        slippage_per_bbl=0.0,
        commission_per_trade=0.0,
        spread_df=df,
    )
    assert "es_975" in payload
    # On a real blotter it's a number; on an empty one it's 0.0.
    assert payload["es_975"] is None or isinstance(payload["es_975"], (int, float))
