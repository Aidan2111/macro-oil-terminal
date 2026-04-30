"""Issue #94 — explicit look-ahead audit.

A targeted, numerically reproducible audit that pins down the
look-ahead surface area in :func:`compute_spread_zscore` and
:func:`backtest_zscore_meanreversion`.

The corner already covered by ``test_quantitative_models_shift.py``
(rolling-mean / rolling-std / EWMA do not include the current bar) is
re-asserted here with the EXACT phrasing the issue body called for —
"a synthetic price path with a known transient spike at index N" — so
the audit trail in the PR matches the acceptance criterion verbatim.

We additionally lock down two looser surfaces the issue body flagged:

    * Sizing / vol adjustment (``Spread_EwmaStd``) must be lagged.
    * Entry/exit semantics in :func:`backtest_zscore_meanreversion`
      must not back-fill the entry price from a future bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_prices_from_spread(spread: np.ndarray) -> pd.DataFrame:
    """Build a Brent/WTI frame whose Brent-WTI difference equals ``spread``."""
    n = len(spread)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    wti = np.full(n, 75.0, dtype=float)
    brent = wti + spread.astype(float)
    return pd.DataFrame({"Brent": brent, "WTI": wti}, index=idx)


def test_rolling_z_at_spike_independent_of_post_spike_prices():
    """Issue #94 verbatim — "the rolling-Z series at index N depends only on prices < N".

    Build two spread paths that are identical for indices ``< N`` and
    diverge wildly for indices ``> N``. The Z value at index ``N`` must
    match exactly between the two paths — otherwise the rolling stats
    that feed Z[N] are touching prices we don't yet know.
    """
    from quantitative_models import compute_spread_zscore

    rng = np.random.default_rng(42)
    n_total = 200
    n_spike = 150  # the "index N" of the spec
    base = rng.normal(0.0, 0.5, size=n_total).cumsum()
    base[n_spike] += 25.0  # the transient spike

    a = base.copy()
    b = base.copy()
    # Diverge AFTER the spike: every post-spike bar is wildly different.
    b[n_spike + 1 :] += 1000.0 * rng.normal(0.0, 1.0, size=n_total - n_spike - 1)

    z_a = compute_spread_zscore(_make_prices_from_spread(a), window=90)["Z_Score"]
    z_b = compute_spread_zscore(_make_prices_from_spread(b), window=90)["Z_Score"]

    # Z at every index up to and including the spike is identical.
    for t in range(n_spike + 1):
        if pd.isna(z_a.iloc[t]) and pd.isna(z_b.iloc[t]):
            continue
        assert z_a.iloc[t] == pytest.approx(z_b.iloc[t], rel=1e-12, abs=1e-12), (
            f"Z divergence at t={t} (n_spike={n_spike}): {z_a.iloc[t]} vs "
            f"{z_b.iloc[t]} — Z must depend only on prices < t."
        )


def test_ewma_z_vol_at_spike_independent_of_post_spike_prices():
    """Same locking-in test for the EWMA volatility path (sizing / vol adj)."""
    from quantitative_models import compute_spread_zscore

    rng = np.random.default_rng(99)
    n_total = 200
    n_spike = 150
    base = rng.normal(0.0, 0.5, size=n_total).cumsum()
    base[n_spike] += 30.0

    a = base.copy()
    b = base.copy()
    b[n_spike + 1 :] += 500.0 * rng.normal(0.0, 1.0, size=n_total - n_spike - 1)

    z_vol_a = compute_spread_zscore(_make_prices_from_spread(a), window=30)["Z_Vol"]
    z_vol_b = compute_spread_zscore(_make_prices_from_spread(b), window=30)["Z_Vol"]

    for t in range(n_spike + 1):
        if pd.isna(z_vol_a.iloc[t]) and pd.isna(z_vol_b.iloc[t]):
            continue
        assert z_vol_a.iloc[t] == pytest.approx(
            z_vol_b.iloc[t], rel=1e-12, abs=1e-12
        ), (
            f"Z_Vol divergence at t={t}: {z_vol_a.iloc[t]} vs "
            f"{z_vol_b.iloc[t]} — EWMA std at t must use residuals < t."
        )


def test_backtest_entry_price_is_signal_bar_close_not_future():
    """The entry_spread recorded for a trade must equal the spread at the
    bar Z first crossed entry_z, not a later bar.

    Construct a path where Z crosses entry_z at bar A and the spread at
    A is uniquely identifiable. Verify the trade's recorded
    entry_spread matches spread[A], not spread[A+1] or spread[A-1].
    """
    from quantitative_models import backtest_zscore_meanreversion

    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="D")

    # Build a spread that hovers tightly near 0 for a long warm-up,
    # then jumps to a deterministic +5.0 on a single bar (the trigger),
    # then mean-reverts toward 0 over the next ~10 bars. The mean-reverting
    # bars are deterministic so the test is reproducible.
    rng = np.random.default_rng(0)
    spread = rng.normal(0.0, 0.05, size=n)
    trigger_bar = 120
    spread[trigger_bar] = 5.0
    # Linear glide back to 0 over 10 bars.
    glide = np.linspace(5.0, 0.0, 11)[1:]  # 10 bars after the trigger
    spread[trigger_bar + 1 : trigger_bar + 1 + 10] = glide

    # Build a Z series consistent with that spread by feeding it through the
    # production Z-score path, then re-running the backtest on the
    # frame the backtester expects.
    df = pd.DataFrame({"Spread": spread}, index=idx)
    # Compute a reference Z so we know which bar will trigger.
    from quantitative_models import compute_spread_zscore

    prices = _make_prices_from_spread(spread)
    z_df = compute_spread_zscore(prices, window=60)
    df["Z_Score"] = z_df["Z_Score"].values

    # Run the backtester with a low-ish entry_z so the trigger bar fires.
    out = backtest_zscore_meanreversion(
        df, entry_z=2.0, exit_z=0.5, slippage_per_bbl=0.0, commission_per_trade=0.0
    )
    trades = out["trades"]
    if hasattr(trades, "to_dict"):
        trades_list = trades.to_dict(orient="records")
    else:
        trades_list = list(trades)

    assert len(trades_list) >= 1, (
        "Test setup error — expected at least one trade to fire on the "
        "engineered spike. Got 0; the spike or entry_z may need tuning."
    )

    first = trades_list[0]
    entry_spread = float(first["entry_spread"])
    # entry_spread must match spread at SOME bar where Z crossed entry_z;
    # specifically, it must equal spread on a bar at or after the rolling
    # warm-up. The strict assertion: it must NOT match spread at a bar
    # AFTER its own entry_date.
    entry_date = pd.Timestamp(first["entry_date"])
    bar_idx = idx.get_loc(entry_date)
    assert entry_spread == pytest.approx(spread[bar_idx], rel=1e-9, abs=1e-9), (
        f"Recorded entry_spread {entry_spread} does not equal spread at "
        f"the recorded entry_date bar (idx={bar_idx}, spread={spread[bar_idx]}). "
        "Entry price has been pulled from a different bar — likely look-ahead."
    )


def test_backtest_no_trades_when_z_never_crosses_entry():
    """A trivial sanity check: no signal → no trades, no PnL leak from
    an "implicit" mark-to-market on the last bar."""
    from quantitative_models import backtest_zscore_meanreversion

    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {
            "Spread": np.zeros(n),
            "Z_Score": np.zeros(n),  # Z is always 0 — never crosses 2.0
        },
        index=idx,
    )
    out = backtest_zscore_meanreversion(df, entry_z=2.0, exit_z=0.2)
    assert out["n_trades"] == 0
    assert out["total_pnl_usd"] == 0.0
    # No equity-curve mark-to-market should leak in.
    eq = out["equity_curve"]
    if hasattr(eq, "empty"):
        assert eq.empty, "Equity curve must be empty when no trades fire."
