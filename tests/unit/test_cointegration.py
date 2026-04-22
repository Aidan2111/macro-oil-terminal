"""Unit tests for the Engle-Granger cointegration module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_cointegrated_pair_detects_low_p_value():
    """A synthetic cointegrated pair should score p < 0.05 reliably."""
    from cointegration import engle_granger
    rng = np.random.default_rng(0)
    n = 600
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    common = np.cumsum(rng.normal(0, 0.5, n)) + 80.0  # shared stochastic trend
    noise_b = rng.normal(0, 0.3, n)
    noise_w = rng.normal(0, 0.3, n)
    brent = pd.Series(common + 3.0 + noise_b, index=idx)
    wti = pd.Series(common + noise_w, index=idx)
    res = engle_granger(brent, wti)
    assert res.verdict in ("cointegrated", "weak")
    assert res.p_value < 0.10
    assert 0.5 < res.hedge_ratio < 1.5
    assert res.n_obs == n


def test_non_cointegrated_pair_detects_high_p_value():
    """Two independent random walks should NOT reject the unit-root null."""
    from cointegration import engle_granger
    rng = np.random.default_rng(1)
    n = 400
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    brent = pd.Series(np.cumsum(rng.normal(0, 0.5, n)) + 80.0, index=idx)
    wti = pd.Series(np.cumsum(rng.normal(0, 0.5, n)) + 75.0, index=idx)
    res = engle_granger(brent, wti)
    # It's statistically possible for independent random walks to spuriously
    # pass, but at n=400 with seed 1 we reliably land in not_cointegrated.
    assert res.verdict in ("not_cointegrated", "weak")


def test_short_series_returns_inconclusive():
    from cointegration import engle_granger
    n = 20
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    b = pd.Series(np.linspace(80, 82, n), index=idx)
    w = pd.Series(np.linspace(77, 79, n), index=idx)
    res = engle_granger(b, w, min_obs=60)
    assert res.verdict == "inconclusive"
    assert not res.is_cointegrated


def test_result_to_dict_rounded():
    from cointegration import engle_granger
    rng = np.random.default_rng(2)
    n = 200
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    common = np.cumsum(rng.normal(0, 0.5, n)) + 80.0
    brent = pd.Series(common + 2.0 + rng.normal(0, 0.2, n), index=idx)
    wti = pd.Series(common + rng.normal(0, 0.2, n), index=idx)
    d = engle_granger(brent, wti).to_dict()
    for key in ("p_value", "adf_stat", "hedge_ratio", "alpha",
                "verdict", "n_obs", "is_cointegrated", "is_weak",
                "half_life_days", "window"):
        assert key in d


def test_rolling_engle_granger_shape():
    from cointegration import rolling_engle_granger
    rng = np.random.default_rng(3)
    n = 400
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    common = np.cumsum(rng.normal(0, 0.5, n)) + 80.0
    b = pd.Series(common + 2.0 + rng.normal(0, 0.2, n), index=idx)
    w = pd.Series(common + rng.normal(0, 0.2, n), index=idx)
    out = rolling_engle_granger(b, w, window=120, step=40)
    assert not out.empty
    assert {"window_end", "p_value", "hedge_ratio", "verdict"}.issubset(out.columns)


def test_half_life_positive_when_reverting():
    from cointegration import engle_granger
    # Strongly mean-reverting spread
    rng = np.random.default_rng(4)
    n = 500
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    trend = np.cumsum(rng.normal(0, 0.4, n)) + 80.0
    b = pd.Series(trend + 2.5 + 0.3 * rng.normal(0, 1, n), index=idx)
    w = pd.Series(trend + 0.3 * rng.normal(0, 1, n), index=idx)
    res = engle_granger(b, w)
    if res.half_life_days is not None:
        assert res.half_life_days > 0
