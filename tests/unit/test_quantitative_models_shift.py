"""Regression tests for Row 1 of docs/reviews/_synthesis.md.

The rolling mean/std that feed the Z-score must exclude the current bar
(``t`` itself) so that signal-at-close-of-``t`` is knowable without peeking
at ``spread[t]``. Previously the pandas-default right-closed window
``[t-W+1, t]`` contaminated every Z computation — a spike at ``t``
appeared in both numerator and denominator-window, which pulled |Z|
toward zero on exactly the bar the backtest transacts on.

These four tests lock in the fix (``shift(1).rolling(W)`` semantics on
both the classic rolling-std path and the EWMA ``Z_Vol`` path) and will
fail against any future regression that removes the shift.

See also Persona 01 (Stats) Finding #1 and Persona 04 (ML) F3 for the
full problem statement.
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


def test_zscore_excludes_current_bar_contribution():
    """99 zeros then a spike of 100 must produce a very large |Z| at the spike.

    Under the leaky same-bar window, the spike appears in both the mean
    and the std for its own bar, so |Z| collapses toward a small number
    (empirically ~9.95 — but the point is the spike is NOT many orders
    of magnitude above its own vol estimate).

    Under the fix, the mean and std at bar 99 are taken from bars
    [10, 98] — all zeros — so the denominator is 0, handled by the
    ``std.replace(0, np.nan)`` guard; the Z at 99 is NaN. A cleaner
    contrast uses a series with small prior noise:
    """
    from quantitative_models import compute_spread_zscore

    rng = np.random.default_rng(0)
    # 99 bars of tiny noise (so prior std is small but non-zero),
    # then one huge spike at bar 99.
    tiny = rng.normal(0.0, 0.01, size=99)
    spread = np.concatenate([tiny, [100.0]])
    prices = _make_prices_from_spread(spread)

    out = compute_spread_zscore(prices, window=90)
    z_last = out["Z_Score"].iloc[-1]

    # Under the fix, rolling stats at t=99 see only the tiny-noise window
    # so |Z| at the spike must be ENORMOUS — far above any reasonable
    # under-leakage value. Under leakage, |Z| is bounded near sqrt(window)
    # because the spike dominates its own sample.
    assert np.isfinite(z_last), "Z_Score at the spike must be finite after the fix"
    # Under leakage the spike is in its own window; |Z| is bounded near
    # sqrt(window) ≈ 9.49 for a 90-bar window (the spike dominates
    # both numerator and denominator-window). Under the fix, the prior
    # window is ~99 bars of 0.01σ noise and the spike is 100 — so |Z|
    # is on the order of 100 / 0.01 = 10,000.
    assert abs(z_last) > 500.0, (
        f"Expected |Z| >> 500 after the shift(1) fix; got {z_last:.4f}. "
        "A value near sqrt(window) (~10) means the spike is still inside "
        "its own rolling window — the same-bar look-ahead has returned."
    )


def test_zscore_agrees_with_manual_shifted_calculation():
    """The public Z at bar t equals manual ``(s[t] - mean(s[t-W:t])) / std(s[t-W:t])``."""
    from quantitative_models import compute_spread_zscore

    rng = np.random.default_rng(123)
    n = 300
    window = 30
    spread = np.cumsum(rng.normal(0.0, 0.25, size=n))
    prices = _make_prices_from_spread(spread)

    out = compute_spread_zscore(prices, window=window)

    # Pick a few bars well past the warm-up and compare.
    spread_series = pd.Series(spread)
    for t in (window + 5, window + 50, n - 1):
        prior = spread_series.iloc[t - window : t]  # closed-left, open-right
        expected_mean = prior.mean()
        expected_std = prior.std(ddof=1)  # pandas rolling default
        if expected_std == 0 or not np.isfinite(expected_std):
            continue
        expected_z = (spread[t] - expected_mean) / expected_std
        got = out["Z_Score"].iloc[t]
        assert np.isfinite(got), f"Z at t={t} unexpectedly NaN/inf"
        assert got == pytest.approx(expected_z, rel=1e-8, abs=1e-10), (
            f"Z mismatch at t={t}: got {got}, expected {expected_z}. "
            "Rolling window is NOT shifted by one bar."
        )


def test_zscore_early_bars_are_nan():
    """With shift(1).rolling(W), the first W bars must be NaN.

    ``shift(1)`` drops bar 0, so the first non-NaN Z is at bar ``W``
    (where the window [0, W-1] is fully populated). But the code uses a
    ``min_periods = max(5, window // 3)`` relaxation, so NaN coverage
    only goes through bar ``min_periods - 1`` — after which partial
    windows start producing values.

    The strict contract we lock in: bar 0 (the spread point with no
    prior history at all) must be NaN.
    """
    from quantitative_models import compute_spread_zscore

    rng = np.random.default_rng(7)
    spread = rng.normal(0.0, 1.0, size=200)
    prices = _make_prices_from_spread(spread)

    out = compute_spread_zscore(prices, window=30)

    # Bar 0 can never have any prior history under the shifted window.
    assert pd.isna(out["Z_Score"].iloc[0]), (
        "Z_Score at bar 0 must be NaN under shift(1).rolling — "
        "there is no prior window to compute from."
    )
    # The last bar with no prior data at all under min_periods must be NaN.
    # min_periods = max(5, 30 // 3) = 10. shift(1) + min_periods=10 means
    # bars 0..9 have fewer than 10 prior observations and must be NaN.
    # (bar 9 has prior [bar 0..8] = 9 obs < 10.)
    assert out["Z_Score"].iloc[:10].isna().all(), (
        "Bars 0..9 should be NaN under shift(1) + min_periods=10; "
        "same-bar look-ahead has returned."
    )


def test_ewma_z_vol_is_shifted():
    """The EWMA Z_Vol path must also exclude its own bar from its own vol.

    Inject a spike at bar 99 after 99 tiny-noise bars. Under the fix, the
    EWMA std at the spike is computed from residuals up through bar 98
    only, so |Z_Vol| at the spike is very large. Under the pre-fix
    leaky path, the spike feeds into its own ewm().mean() and the
    resulting |Z_Vol| is much smaller.
    """
    from quantitative_models import compute_spread_zscore

    rng = np.random.default_rng(1)
    tiny = rng.normal(0.0, 0.01, size=99)
    spread = np.concatenate([tiny, [100.0]])
    prices = _make_prices_from_spread(spread)

    out = compute_spread_zscore(prices, window=30)
    z_vol_last = out["Z_Vol"].iloc[-1]

    assert np.isfinite(z_vol_last), "Z_Vol at the spike must be finite after the fix"
    # Under the pre-fix leaky EWMA, the spike's squared residual feeds
    # into its own ewm variance — the first-bar weighting (1 - λ) = 0.06
    # of a 10,000-unit residual dominates ewm_var, bringing |Z_Vol| down
    # to ~4. Under the fix, the ewm variance at the spike is whatever it
    # was at bar 98 (tiny), so |Z_Vol| becomes ~O(100 / tiny_std).
    assert abs(z_vol_last) > 50.0, (
        f"Expected |Z_Vol| >> 50 after shifting the EWMA path; "
        f"got {z_vol_last:.4f}. A value ~4 means the spike is still in "
        "its own EWMA variance window — same-bar leakage in Spread_EwmaStd."
    )
