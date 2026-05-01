"""Issue #97 — yfinance vs FRED price-corroboration unit tests.

Acceptance criteria from the issue body:
  * mock yfinance returning 100, FRED returning 105, assert envelope
    amber + delta = 0.05 (5%).
  * mock both providers ≈ same number, envelope green, delta < 0.02.
"""

from __future__ import annotations

import pytest

from backend.services.spread_service import (
    PRICE_CORROBORATION_THRESHOLD,
    _max_relative_delta,
    corroborate_with_fred,
)


def _stub_fred(brent: float | None, wti: float | None):
    def _fn():
        return {"brent": brent, "wti": wti}
    return _fn


def test_max_relative_delta_handles_missing_legs():
    """If FRED is missing one leg, fall back to the leg that exists."""
    yf = {"brent": 100.0, "wti": 80.0}
    fred = {"brent": 102.0, "wti": None}
    delta = _max_relative_delta(yf, fred)
    # 2 / 102 ≈ 0.01961
    assert delta == pytest.approx(2.0 / 102.0, rel=1e-9)

    # Both legs missing -> None.
    assert _max_relative_delta(yf, {"brent": None, "wti": None}) is None


def test_corroboration_amber_when_divergence_above_threshold():
    """Issue body — yf=100, FRED=105 -> amber + delta=0.0476..."""
    snap, degraded, msg = corroborate_with_fred(
        brent_yf=100.0, wti_yf=100.0,
        fetch_fn=_stub_fred(105.0, 105.0),
    )
    assert snap.yfinance == {"brent": 100.0, "wti": 100.0}
    assert snap.fred == {"brent": 105.0, "wti": 105.0}
    # max(|100-105|/105) = 5/105 ≈ 0.0476
    assert snap.max_relative_delta == pytest.approx(0.0476, abs=1e-3)
    assert degraded is True
    assert msg is not None and "price-source divergence" in msg


def test_corroboration_green_when_within_threshold():
    """yf and FRED within 0.5% -> green, no degradation."""
    snap, degraded, msg = corroborate_with_fred(
        brent_yf=108.23, wti_yf=96.37,
        fetch_fn=_stub_fred(108.05, 96.41),
    )
    assert snap.max_relative_delta is not None
    assert snap.max_relative_delta < PRICE_CORROBORATION_THRESHOLD
    assert snap.max_relative_delta < 0.02
    assert degraded is False
    assert msg is None


def test_corroboration_skips_when_fred_unavailable():
    """If FRED returns all-None, the snapshot has delta=None and
    no degradation is reported (next-day delay is normal)."""
    def _empty():
        return {"brent": None, "wti": None}

    snap, degraded, msg = corroborate_with_fred(
        brent_yf=100.0, wti_yf=80.0, fetch_fn=_empty,
    )
    assert snap.fred == {"brent": None, "wti": None}
    assert snap.max_relative_delta is None
    assert degraded is False
    assert msg is None


def test_corroboration_handles_fred_fetch_exception():
    """FRED fetch raising must NOT crash the spread response — we
    swallow + return all-None."""
    def _boom():
        raise RuntimeError("FRED 503")

    snap, degraded, msg = corroborate_with_fred(
        brent_yf=100.0, wti_yf=80.0, fetch_fn=_boom,
    )
    assert snap.fred == {"brent": None, "wti": None}
    assert degraded is False
    assert msg is None


def test_threshold_boundary_just_under_2pct_is_green():
    """Boundary check — yf=100 vs FRED=102 gives delta = 2/102 ≈ 1.96%,
    which is below the 2% threshold, so the envelope must stay green."""
    yf = {"brent": 100.0, "wti": 100.0}
    fred = {"brent": 102.0, "wti": 102.0}
    delta = _max_relative_delta(yf, fred)
    assert delta == pytest.approx(2.0 / 102.0, rel=1e-9)
    assert delta < PRICE_CORROBORATION_THRESHOLD
    snap, degraded, msg = corroborate_with_fred(
        brent_yf=100.0, wti_yf=100.0,
        fetch_fn=_stub_fred(102.0, 102.0),
    )
    assert degraded is False
    assert msg is None


def test_threshold_boundary_just_over_2pct_is_amber():
    """Mirror — yf=100 vs FRED=97 gives delta = 3/97 ≈ 3.09%, well
    above the 2% threshold, so envelope must flip to amber."""
    yf = {"brent": 100.0, "wti": 100.0}
    fred = {"brent": 97.0, "wti": 97.0}
    delta = _max_relative_delta(yf, fred)
    assert delta > PRICE_CORROBORATION_THRESHOLD
    snap, degraded, msg = corroborate_with_fred(
        brent_yf=100.0, wti_yf=100.0,
        fetch_fn=_stub_fred(97.0, 97.0),
    )
    assert degraded is True
    assert msg is not None and "price-source divergence" in msg
