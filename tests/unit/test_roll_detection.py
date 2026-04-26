"""Unit tests for backend.services.roll_detection.

Strategy: build a synthetic Brent-WTI spread series with one engineered
2.5% gap on a known CME-published roll date, plus a 2.5% gap on a NON-
roll date, plus some <1% noise. Detector must catch the first and
ignore the others.
"""

from __future__ import annotations

import sys
import pathlib
from datetime import date

import numpy as np
import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.roll_detection import (  # noqa: E402
    annotate_history_with_rolls,
    detect_front_month_rolls,
)


def _build_series_with_gaps() -> pd.DataFrame:
    """40 trading days starting 2026-04-01 with two engineered gaps."""
    dates = pd.bdate_range("2026-04-01", periods=40)
    rng = np.random.default_rng(42)
    base = 4.0 + rng.normal(0, 0.05, size=len(dates)).cumsum() * 0.05
    spread = base.copy()

    df = pd.DataFrame({"Spread": spread}, index=dates)

    # Engineered roll gap — 2026-04-30 is in the bundled calendar.
    roll_idx = df.index.get_indexer([pd.Timestamp("2026-04-30")])[0]
    if roll_idx > 0:
        df.iloc[roll_idx, 0] = df.iloc[roll_idx - 1, 0] * 1.025

    # Engineered non-roll gap — 2026-04-15 is far from any calendar entry.
    non_roll_idx = df.index.get_indexer([pd.Timestamp("2026-04-15")])[0]
    if non_roll_idx > 0:
        df.iloc[non_roll_idx, 0] = df.iloc[non_roll_idx - 1, 0] * 1.025

    return df


def test_detects_known_roll_and_ignores_non_roll_gap():
    df = _build_series_with_gaps()
    rolls = detect_front_month_rolls(df)
    assert date(2026, 4, 30) in rolls
    assert date(2026, 4, 15) not in rolls


def test_empty_or_malformed_df_returns_empty_list():
    assert detect_front_month_rolls(pd.DataFrame()) == []
    assert detect_front_month_rolls(pd.DataFrame({"Spread": []})) == []
    assert detect_front_month_rolls(pd.DataFrame({"WrongCol": [1, 2, 3]})) == []
    assert detect_front_month_rolls(None) == []


def test_annotate_history_marks_only_roll_points():
    history = [
        {"date": "2026-04-29", "spread": 4.1},
        {"date": "2026-04-30", "spread": 4.3},
        {"date": "2026-05-01", "spread": 4.32},
    ]
    rolls = [date(2026, 4, 30)]
    out = annotate_history_with_rolls(history, rolls)
    assert [p["is_roll"] for p in out] == [False, True, False]
    # original list untouched
    assert "is_roll" not in history[0]


def test_custom_calendar_widens_detection():
    """If a caller passes a custom calendar, the detector should use
    it instead of the hard-coded one."""
    df = _build_series_with_gaps()
    rolls = detect_front_month_rolls(
        df,
        calendar=[date(2026, 4, 15)],
        tolerance_bdays=1,
    )
    assert date(2026, 4, 15) in rolls
