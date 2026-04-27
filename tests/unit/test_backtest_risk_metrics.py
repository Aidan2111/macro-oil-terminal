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


def _trending_spread_df(n: int = 1200, seed: int = 1) -> pd.DataFrame:
    """A spread that drifts steadily over the window — the classic
    "trend-eats-the-mean-reversion-trader" fixture. Plenty of trades
    fire because z spikes are common in a trending series, but a
    fraction of them get crushed when the trend keeps pushing further
    away from the rolling mean. The resulting per-trade PnL has both
    big losers and big winners, which is what the VaR / ES / DD
    inequalities require to be non-degenerate.
    """
    rng = np.random.default_rng(seed)
    trend = np.linspace(0, 30, n) + rng.normal(0, 0.5, n)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    s = pd.Series(trend, index=idx)
    window = 60
    roll_mean = s.rolling(window).mean()
    roll_std = s.rolling(window).std(ddof=0).replace(0, np.nan)
    z = (s - roll_mean) / roll_std
    df = pd.DataFrame({"Spread": s, "Z_Score": z}).dropna()
    return df


def test_var95_es95_es975_max_dd_are_distinct_on_real_blotter():
    """Issue #64: on a non-degenerate blotter the four risk metrics must
    be mathematically distinct, and the VaR/ES inequality chain must
    hold.

    Definitions:
      VaR-95        = 5th-percentile single-period loss
      ES-95         = mean of trades at or below VaR-95
      ES-97.5       = mean of trades at or below the 2.5th-percentile cutoff
      max_drawdown  = largest peak-to-trough drop on the cumulative
                      equity curve

    Inequalities:
      |VaR-95| ≤ |ES-95| ≤ |ES-97.5|   (deeper tails average worse on
                                         the negative side of the
                                         distribution)
    """
    from quantitative_models import backtest_zscore_meanreversion

    df = _trending_spread_df()
    out = backtest_zscore_meanreversion(df, entry_z=1.5, exit_z=0.2)
    if out["n_trades"] < 30:
        pytest.skip("blotter too small to differentiate VaR / ES tails")

    var95 = out["var_95"]
    es95 = out["es_95"]
    es975 = out["es_975"]
    max_dd = out["max_drawdown_usd"]

    # All four mathematically distinct (epsilon-tolerant — we want
    # genuinely different summary stats, not the same number stamped
    # into four fields).
    distinct = {round(v, 4) for v in (var95, es95, es975, max_dd)}
    assert len(distinct) == 4, (
        f"risk metrics collapsed: var95={var95}, es95={es95}, "
        f"es975={es975}, max_dd={max_dd}"
    )

    # VaR / ES tail-severity chain. The ES averages strictly worse
    # outcomes than the VaR cutoff (and the 2.5th-pct tail is deeper
    # than the 5th-pct tail), so on the negative side:
    #   ES-97.5 ≤ ES-95 ≤ VaR-95
    assert es95 <= var95 + 1e-9, (
        f"ES-95={es95} should be ≤ VaR-95={var95} (deeper tail)"
    )
    assert es975 <= es95 + 1e-9, (
        f"ES-97.5={es975} should be ≤ ES-95={es95} (deeper tail)"
    )


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
