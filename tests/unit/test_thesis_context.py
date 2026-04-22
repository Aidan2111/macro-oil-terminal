"""Unit tests for the thesis_context helpers."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def test_percentile_rank():
    from thesis_context import _percentile_rank
    s = pd.Series([1, 2, 3, 4, 5])
    assert _percentile_rank(s, 3) == 60.0
    assert _percentile_rank(s, 0) == 0.0
    assert _percentile_rank(s, 9) == 100.0
    assert _percentile_rank(pd.Series([], dtype=float), 0) == 50.0


def test_linear_slope_per_day():
    from thesis_context import _linear_slope_per_day
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    s = pd.Series(np.arange(10, dtype=float), index=idx)
    assert math.isclose(_linear_slope_per_day(s), 1.0, abs_tol=1e-9)
    # Constant series → ~zero slope (allow float-noise)
    s2 = pd.Series(np.ones(10), index=idx)
    assert abs(_linear_slope_per_day(s2)) < 1e-9


def test_realized_vol_nonneg():
    from thesis_context import _realized_vol_pct
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    rng = np.random.default_rng(0)
    s = pd.Series(100.0 + np.cumsum(rng.normal(0, 0.5, 60)), index=idx)
    assert _realized_vol_pct(s, 30) >= 0


def test_days_since_last_abs_z_over():
    from thesis_context import _days_since_last_abs_z_over
    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    vals = [0.1] * 30
    vals[10] = 2.5  # one extreme 20 days ago
    s = pd.Series(vals, index=idx)
    out = _days_since_last_abs_z_over(s, 2.0)
    assert out == 19  # 30 - 1 - 10


def test_next_wednesday_always_after_today():
    from thesis_context import _next_wednesday
    today = pd.Timestamp("2026-04-22")  # Wednesday
    nxt = _next_wednesday(today)
    assert nxt > today
    assert nxt.weekday() == 2
