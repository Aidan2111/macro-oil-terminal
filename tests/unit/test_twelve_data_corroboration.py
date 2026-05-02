"""Issue #106 — Twelve Data as third corroboration source.

Acceptance:
  * Twelve Data leg appears in CorroborationSnapshot when keyed.
  * Three-source pairwise check fires amber when ANY pair diverges.
  * Twelve Data unavailable -> snapshot still works on yf + FRED only.
"""

from __future__ import annotations

import pytest

from backend.services.spread_service import (
    PRICE_CORROBORATION_THRESHOLD,
    _pair_relative_delta,
    _pairwise_max_delta,
    corroborate_with_fred,
)


def _stub_fred(brent: float | None, wti: float | None):
    def _fn():
        return {"brent": brent, "wti": wti}
    return _fn


def _stub_td(brent: float | None, wti: float | None):
    def _fn():
        return {"brent": brent, "wti": wti}
    return _fn


# ---------------------------------------------------------------------------
# Pairwise helper
# ---------------------------------------------------------------------------
def test_pair_relative_delta_skips_when_either_leg_missing():
    a = {"brent": 100.0, "wti": 80.0}
    b = {"brent": None, "wti": 80.5}
    delta = _pair_relative_delta(a, b)
    # Only WTI overlaps -> 0.5 / 80.5 ≈ 0.0062
    assert delta == pytest.approx(0.5 / 80.5, rel=1e-6)


def test_pair_relative_delta_returns_none_when_no_overlap():
    a = {"brent": 100.0, "wti": None}
    b = {"brent": None, "wti": 80.0}
    assert _pair_relative_delta(a, b) is None


def test_pairwise_max_delta_picks_worst_across_three_sources():
    snapshots = {
        "yfinance": {"brent": 100.0, "wti": 100.0},
        "fred": {"brent": 100.5, "wti": 100.0},
        "twelve_data": {"brent": 110.0, "wti": 100.0},  # 10/110 off yfinance
    }
    delta = _pairwise_max_delta(snapshots)
    # Worst pair: yfinance vs twelve_data brent leg → |100-110|/110 ≈ 0.0909.
    assert delta == pytest.approx(10.0 / 110.0, rel=1e-6)


def test_pairwise_max_delta_returns_none_when_only_one_source():
    delta = _pairwise_max_delta({"yfinance": {"brent": 100.0, "wti": 80.0}})
    assert delta is None


# ---------------------------------------------------------------------------
# Three-source corroborate_with_fred
# ---------------------------------------------------------------------------
def test_three_source_snapshot_includes_twelve_data_leg():
    snap, degraded, msg = corroborate_with_fred(
        brent_yf=108.0, wti_yf=96.0,
        fetch_fn=_stub_fred(108.05, 96.05),
        twelve_data_fn=_stub_td(108.10, 96.10),
    )
    assert snap.twelve_data == {"brent": 108.10, "wti": 96.10}
    assert snap.fred == {"brent": 108.05, "wti": 96.05}
    assert snap.yfinance == {"brent": 108.0, "wti": 96.0}
    assert degraded is False
    assert msg is None


def test_amber_fires_when_twelve_data_diverges_from_yfinance():
    """yfinance + FRED agree, but Twelve Data is 5% off — amber fires."""
    snap, degraded, msg = corroborate_with_fred(
        brent_yf=100.0, wti_yf=100.0,
        fetch_fn=_stub_fred(100.0, 100.0),
        twelve_data_fn=_stub_td(108.0, 108.0),
    )
    assert degraded is True
    assert msg is not None
    assert "twelve_data" in msg or "twelve_data" in msg.replace("_", " ")
    assert snap.max_relative_delta is not None
    assert snap.max_relative_delta > PRICE_CORROBORATION_THRESHOLD


def test_no_twelve_data_unkeyed_falls_back_to_two_source():
    """When Twelve Data returns all-None (unkeyed), corroboration still
    runs on yfinance + FRED only and the snapshot omits the TD leg
    from the pairwise comparison."""
    snap, degraded, msg = corroborate_with_fred(
        brent_yf=108.0, wti_yf=96.0,
        fetch_fn=_stub_fred(108.05, 96.05),
        twelve_data_fn=lambda: {"brent": None, "wti": None},
    )
    assert snap.twelve_data == {"brent": None, "wti": None}
    assert degraded is False
    # Worst pair = yfinance vs FRED.
    assert snap.max_relative_delta is not None
    assert snap.max_relative_delta < PRICE_CORROBORATION_THRESHOLD


def test_twelve_data_fetch_exception_swallowed_safely():
    """A Twelve Data fetcher that raises must NOT crash corroboration
    — corroborate_with_fred swallows the exception and proceeds with
    the remaining sources."""
    def _boom():
        raise RuntimeError("twelvedata 503")

    snap, degraded, msg = corroborate_with_fred(
        brent_yf=100.0, wti_yf=80.0,
        fetch_fn=_stub_fred(100.0, 80.0),
        twelve_data_fn=_boom,
    )
    assert snap.twelve_data == {"brent": None, "wti": None}
    assert degraded is False
    assert msg is None


def test_yfinance_fred_disagreement_still_fires_amber_with_td_present():
    """Old #97 behaviour preserved: yfinance vs FRED 5% gap fires amber
    even when Twelve Data is wired in and agreeing with yfinance."""
    snap, degraded, msg = corroborate_with_fred(
        brent_yf=100.0, wti_yf=100.0,
        fetch_fn=_stub_fred(110.0, 110.0),       # 10% above yfinance
        twelve_data_fn=_stub_td(100.05, 100.05), # near yfinance
    )
    assert degraded is True
    # Worst pair must be yfinance vs FRED.
    assert "fred" in msg
