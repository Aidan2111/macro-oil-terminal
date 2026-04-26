"""Unit tests for backend.services.calibration.

Two synthetic populations:
  * A perfectly-calibrated population — within each bucket, hit-rate
    matches the bucket midpoint.
  * A uniformly-overconfident population — every bucket hit-rate
    falls 25% below midpoint.
"""

from __future__ import annotations

import sys
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.calibration import (  # noqa: E402
    BUCKETS,
    compute_calibration,
)


def _row(prob: float, hit: bool) -> dict:
    return {
        "thesis": {
            "conviction_0_to_10": prob * 10.0,
            "outcome": {"hit_target": hit, "realized_return_pct": 0.01},
        }
    }


def _calibrated_population(per_bucket: int = 40) -> list[dict]:
    """For each bucket, emit rows whose realised hit rate matches midpoint."""
    rows: list[dict] = []
    for lo, hi, _ in BUCKETS:
        mid = (lo + min(hi, 1.0)) / 2.0
        n_hits = round(per_bucket * mid)
        for i in range(per_bucket):
            rows.append(_row(mid, hit=i < n_hits))
    return rows


def _overconfident_population(per_bucket: int = 40) -> list[dict]:
    rows: list[dict] = []
    for lo, hi, _ in BUCKETS:
        mid = (lo + min(hi, 1.0)) / 2.0
        actual = max(0.0, mid - 0.25)
        n_hits = round(per_bucket * actual)
        for i in range(per_bucket):
            rows.append(_row(mid, hit=i < n_hits))
    return rows


def test_calibrated_population_yields_calibrated_verdict():
    stats = compute_calibration(_calibrated_population())
    assert stats.verdict == "calibrated"
    assert abs(stats.mean_signed_error) < 0.05
    assert stats.brier_score <= 0.25  # calibrated != zero brier (variance)
    assert stats.n_total == 4 * 40


def test_overconfident_population_is_flagged():
    stats = compute_calibration(_overconfident_population())
    assert stats.verdict == "overconfident"
    assert stats.mean_signed_error > 0.05


def test_underconfident_population_is_flagged():
    """Inverse of overconfident — actuals beat stated."""
    rows: list[dict] = []
    per_bucket = 40
    for lo, hi, _ in BUCKETS:
        mid = (lo + min(hi, 1.0)) / 2.0
        actual = min(1.0, mid + 0.25)
        n_hits = round(per_bucket * actual)
        for i in range(per_bucket):
            rows.append(_row(mid, hit=i < n_hits))
    stats = compute_calibration(rows)
    assert stats.verdict == "underconfident"
    assert stats.mean_signed_error < -0.05


def test_empty_population_is_insufficient():
    stats = compute_calibration([])
    assert stats.verdict == "insufficient_data"
    assert stats.n_total == 0
    assert len(stats.buckets) == 4


def test_rows_without_outcome_are_skipped():
    rows = [
        {"thesis": {"conviction_0_to_10": 8.0}},  # no outcome
        {"thesis": {"conviction_0_to_10": None, "outcome": {"hit_target": True}}},
        {"thesis": {"conviction_0_to_10": 8.0, "outcome": {"hit_target": True}}},
    ]
    stats = compute_calibration(rows)
    assert stats.n_total == 1
