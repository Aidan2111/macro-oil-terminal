"""Unit tests for backend.services.regime_service.

Three fixtures, one classification each:
  * Brent > WTI  → "contango"
  * Brent < WTI  → "backwardation"
  * Brent ≈ WTI  → "flat"

Plus the vol-bucket sanity:
  * Calm series → "low"
  * Stormy series → "high"

The service must never raise on pathological input — short windows,
missing columns, empty frames all collapse to a populated fallback
with ``message`` set.
"""

from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import pandas as pd


_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _frame(brent_offset: float, vol: float, n: int = 400, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = np.cumsum(rng.normal(0, vol, n)) + 80.0
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Brent": base + brent_offset + rng.normal(0, 0.05, n),
            "WTI": base + rng.normal(0, 0.05, n),
        },
        index=idx,
    )


def test_contango_when_brent_richer_than_wti():
    from backend.services.regime_service import detect_regime
    df = _frame(brent_offset=2.5, vol=0.4)
    rs = detect_regime(df)
    assert rs.term_structure == "contango"
    assert rs.spread_sign > 0


def test_backwardation_when_wti_richer_than_brent():
    from backend.services.regime_service import detect_regime
    df = _frame(brent_offset=-2.5, vol=0.4)
    rs = detect_regime(df)
    assert rs.term_structure == "backwardation"
    assert rs.spread_sign < 0


def test_flat_when_brent_and_wti_nearly_equal():
    from backend.services.regime_service import detect_regime
    df = _frame(brent_offset=0.05, vol=0.4)
    rs = detect_regime(df)
    assert rs.term_structure == "flat"


def _stitched_spread_frame(
    head_vol: float,
    tail_vol: float,
    n_head: int = 250,
    n_tail: int = 60,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a Brent/WTI frame where the *spread* (Brent − WTI) has a
    stitched vol regime: ``head_vol`` for the first ``n_head`` bars and
    ``tail_vol`` for the trailing ``n_tail`` bars.

    Crucially Brent and WTI must NOT share the same random walk —
    otherwise their difference cancels and the spread vol is dominated
    by the i.i.d. tiny noise terms instead of the regime we encoded.
    """
    rng = np.random.default_rng(seed)
    # Independent stochastic trends for the two legs.
    brent_trend = np.cumsum(rng.normal(0, 0.4, n_head + n_tail)) + 82.0
    wti_trend = np.cumsum(rng.normal(0, 0.4, n_head + n_tail)) + 80.0
    # Spread innovations switch from head_vol to tail_vol at the breakpoint.
    spread_inno = np.concatenate(
        [
            rng.normal(0, head_vol, n_head),
            rng.normal(0, tail_vol, n_tail),
        ]
    )
    # Glue the spread regime to Brent (WTI stays as its own random walk).
    brent = wti_trend + 1.5 + spread_inno + rng.normal(0, 0.02, n_head + n_tail)
    wti = wti_trend + rng.normal(0, 0.02, n_head + n_tail)
    idx = pd.date_range("2024-01-01", periods=n_head + n_tail, freq="D")
    return pd.DataFrame({"Brent": brent, "WTI": wti}, index=idx)


def test_high_vol_bucket_when_recent_window_is_stormier_than_history():
    """Calm history then stormy tail → bucket = high."""
    from backend.services.regime_service import detect_regime
    df = _stitched_spread_frame(head_vol=0.1, tail_vol=2.5, seed=42)
    rs = detect_regime(df)
    assert rs.vol_bucket == "high"
    assert math.isfinite(rs.vol_percentile)
    assert rs.vol_percentile > 60.0


def test_low_vol_bucket_when_recent_window_is_calmer_than_history():
    """Stormy history then calm tail → bucket = low."""
    from backend.services.regime_service import detect_regime
    df = _stitched_spread_frame(head_vol=2.5, tail_vol=0.1, seed=11)
    rs = detect_regime(df)
    assert rs.vol_bucket == "low"
    assert rs.vol_percentile < 40.0


def test_short_window_returns_unknown_bucket_without_raising():
    from backend.services.regime_service import detect_regime
    n = 10
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {"Brent": np.linspace(80, 82, n), "WTI": np.linspace(78, 79, n)},
        index=idx,
    )
    rs = detect_regime(df)
    assert rs.vol_bucket == "unknown"
    assert rs.message != ""


def test_empty_frame_falls_back_gracefully():
    from backend.services.regime_service import detect_regime
    rs = detect_regime(pd.DataFrame())
    assert rs.term_structure == "flat"
    assert rs.vol_bucket == "unknown"


def test_to_dict_scrubs_nan_to_none():
    from backend.services.regime_service import detect_regime
    rs = detect_regime(pd.DataFrame())
    d = rs.to_dict()
    # NaN-scrubbing on the JSON-friendly view.
    assert d["vol_percentile"] is None
    assert d["realized_vol_20d_pct"] is None
    assert d["term_structure"] == "flat"
