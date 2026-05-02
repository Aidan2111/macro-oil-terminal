"""Issue #102 — multiple-testing correction unit tests.

Acceptance criteria from the issue body:
  * Synthetic case where raw p < 0.05 but Bonferroni-corrected p > 0.05
    — the correction must kick in.
"""

from __future__ import annotations

import sys
import pathlib

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from quantitative_models import multiple_testing_correction


def test_bonferroni_kicks_in_above_005():
    """Issue body acceptance — raw 0.04 across 5 thresholds becomes
    Bonferroni 0.20 (well above 0.05)."""
    raw = [0.04, 0.30, 0.45, 0.60, 0.80]
    out = multiple_testing_correction(raw)
    # Bonferroni: 0.04 * 5 = 0.20 > 0.05.
    assert out["p_bonferroni"][0] == pytest.approx(0.20)
    assert out["p_bonferroni"][0] > 0.05
    # Raw p was below 0.05, so the correction has materially changed
    # the verdict.
    assert raw[0] < 0.05
    assert out["p_bonferroni"][0] > 0.05


def test_bonferroni_clipped_at_one():
    out = multiple_testing_correction([0.5, 0.6, 0.7, 0.8])
    # 0.7 * 4 = 2.8 → clip to 1.0.
    assert all(p <= 1.0 for p in out["p_bonferroni"])
    assert out["p_bonferroni"][3] == 1.0


def test_bh_more_powerful_than_bonferroni():
    """BH should ≤ Bonferroni in every position (more powerful)."""
    raw = [0.001, 0.01, 0.04, 0.10, 0.30]
    out = multiple_testing_correction(raw)
    bh = np.asarray(out["p_bh"])
    bonf = np.asarray(out["p_bonferroni"])
    assert (bh <= bonf + 1e-9).all(), (
        f"BH not ≤ Bonferroni at every position. bh={bh.tolist()} "
        f"bonf={bonf.tolist()}"
    )


def test_bh_monotonic_after_correction():
    """BH is monotone non-decreasing in the original p-value order
    after the cumulative-min from the right."""
    raw = [0.001, 0.005, 0.04, 0.10, 0.30]
    out = multiple_testing_correction(raw)
    bh_sorted = sorted(zip(raw, out["p_bh"]))
    last = -1.0
    for _, q in bh_sorted:
        assert q >= last - 1e-9, f"BH not monotone: {bh_sorted}"
        last = q


def test_empty_input_returns_empty_arrays():
    out = multiple_testing_correction([])
    assert out["p_raw"] == []
    assert out["p_bonferroni"] == []
    assert out["p_bh"] == []


def test_method_filter_returns_only_requested():
    raw = [0.01, 0.05, 0.10]
    bonf_only = multiple_testing_correction(raw, method="bonferroni")
    assert "p_bonferroni" in bonf_only
    assert "p_bh" not in bonf_only

    bh_only = multiple_testing_correction(raw, method="bh")
    assert "p_bh" in bh_only
    assert "p_bonferroni" not in bh_only


# ---------------------------------------------------------------------------
# Threshold sweep with correction (the integrated function)
# ---------------------------------------------------------------------------
def test_threshold_sweep_returns_aligned_arrays():
    """All four output lists must be the same length as the threshold list."""
    from quantitative_models import threshold_sweep_with_correction

    rng = np.random.default_rng(0)
    n = 600
    spread = np.cumsum(rng.normal(0, 0.4, size=n))
    import pandas as pd

    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    s = pd.Series(spread, index=idx, name="Spread")
    rmean = s.shift(1).rolling(60).mean()
    rstd = s.shift(1).rolling(60).std(ddof=0).replace(0, np.nan)
    z = (s - rmean) / rstd
    df = pd.DataFrame({"Spread": s, "Z_Score": z}).dropna()

    thresholds = [1.0, 1.5, 2.0]
    out = threshold_sweep_with_correction(df, thresholds=thresholds, n_resamples=100)
    assert out["thresholds"] == thresholds
    assert len(out["p_raw"]) == 3
    assert len(out["p_bonferroni"]) == 3
    assert len(out["p_bh"]) == 3
    # All p-values are in [0, 1].
    for key in ("p_raw", "p_bonferroni", "p_bh"):
        for p in out[key]:
            assert 0.0 <= p <= 1.0, f"{key}: {p} out of [0,1]"


def test_threshold_sweep_handles_empty_input():
    from quantitative_models import threshold_sweep_with_correction
    import pandas as pd

    out = threshold_sweep_with_correction(
        pd.DataFrame(), thresholds=[1.0, 2.0]
    )
    assert out["p_raw"] == [1.0, 1.0]
    assert out["p_bonferroni"] == [1.0, 1.0]
    assert out["p_bh"] == [1.0, 1.0]
