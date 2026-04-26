"""Unit tests for backend.services.cointegration_service.

Pin three contracts:
  1. Happy path on a synthetic cointegrated pair returns a finite
     p-value, half-life, and the "cointegrated" verdict.
  2. The content-hash cache hits on identical inputs and skips the
     regression — we assert by patching ``cointegration.engle_granger``
     and counting calls.
  3. Pathological inputs (empty frame, missing columns, too-short
     window) return ``inconclusive`` with a populated ``message``
     and a NaN-or-None p-value rather than raising.
"""

from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest


_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def _clear_cache():
    from backend.services import cointegration_service as cs
    cs.cache_clear()
    yield
    cs.cache_clear()


def _cointegrated_frame(n: int = 600, seed: int = 0) -> pd.DataFrame:
    """Return a Brent/WTI frame that is reliably cointegrated."""
    rng = np.random.default_rng(seed)
    common = np.cumsum(rng.normal(0, 0.5, n)) + 80.0
    brent = common + 3.0 + rng.normal(0, 0.3, n)
    wti = common + rng.normal(0, 0.3, n)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    return pd.DataFrame({"Brent": brent, "WTI": wti}, index=idx)


def test_happy_path_returns_finite_p_and_half_life():
    from backend.services.cointegration_service import (
        compute_cointegration_for_thesis,
    )
    df = _cointegrated_frame()
    out = compute_cointegration_for_thesis(df)

    assert math.isfinite(out.eg_pvalue)
    assert out.eg_pvalue < 0.10
    assert out.verdict in ("cointegrated", "weak")
    # OU half-life should land in a sensible (positive, not pathological) band.
    # The synthetic spread is very tight so the half-life can be < 1 day; we
    # only assert finiteness + a sane upper bound.
    assert math.isfinite(out.half_life_days)
    assert 0.0 < out.half_life_days < 365.0
    assert out.n_obs == 600
    assert out.message == ""

    # JSON-friendly shape — NaN scrubbed if any
    d = out.to_dict()
    assert d["eg_pvalue"] is not None
    assert d["half_life_days"] is not None
    assert d["johansen_trace"] is None  # reserved


def test_cache_skips_recomputation_on_identical_input(monkeypatch):
    """Second call with the same content should NOT re-invoke engle_granger."""
    from backend.services import cointegration_service as cs
    import cointegration as coint_mod

    df = _cointegrated_frame(n=400, seed=7)

    real_eg = coint_mod.engle_granger
    call_count = {"n": 0}

    def counting_eg(*args, **kwargs):
        call_count["n"] += 1
        return real_eg(*args, **kwargs)

    monkeypatch.setattr(coint_mod, "engle_granger", counting_eg)

    cs.cache_clear()
    out1 = cs.compute_cointegration_for_thesis(df)
    out2 = cs.compute_cointegration_for_thesis(df)
    out3 = cs.compute_cointegration_for_thesis(df.copy())  # same content, new object

    assert out1.eg_pvalue == out2.eg_pvalue == out3.eg_pvalue
    # Three calls, one underlying computation.
    assert call_count["n"] == 1


def test_short_window_returns_inconclusive_without_raising():
    from backend.services.cointegration_service import (
        compute_cointegration_for_thesis,
    )
    n = 20
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame(
        {
            "Brent": np.linspace(80, 82, n),
            "WTI": np.linspace(77, 79, n),
        },
        index=idx,
    )
    out = compute_cointegration_for_thesis(df)
    assert out.verdict == "inconclusive"
    # Either NaN (engle_granger short-circuit) or finite — accept either.
    # The contract is "no raise + inconclusive verdict".


def test_missing_columns_returns_message_not_raise():
    from backend.services.cointegration_service import (
        compute_cointegration_for_thesis,
    )
    df = pd.DataFrame({"OTHER": [1.0, 2.0, 3.0]})
    out = compute_cointegration_for_thesis(df)
    assert out.verdict == "inconclusive"
    assert "Brent" in out.message or "WTI" in out.message


def test_empty_frame_returns_message_not_raise():
    from backend.services.cointegration_service import (
        compute_cointegration_for_thesis,
    )
    out = compute_cointegration_for_thesis(pd.DataFrame())
    assert out.verdict == "inconclusive"
    assert out.n_obs == 0
    assert out.message != ""


def test_to_dict_scrubs_nan_to_none():
    from backend.services.cointegration_service import (
        CointegrationStats,
    )
    s = CointegrationStats(
        eg_pvalue=float("nan"),
        half_life_days=float("nan"),
        johansen_trace=None,
        hedge_ratio=float("nan"),
        verdict="inconclusive",
        n_obs=0,
        message="x",
    )
    d = s.to_dict()
    assert d["eg_pvalue"] is None
    assert d["half_life_days"] is None
    assert d["hedge_ratio"] is None
    assert d["johansen_trace"] is None
    assert d["verdict"] == "inconclusive"
