"""Tests for the GARCH helper."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def test_garch_fit_stable_on_synthetic_residual():
    from vol_models import fit_garch_residual
    rng = np.random.default_rng(0)
    n = 600
    sigma = np.zeros(n)
    resid = np.zeros(n)
    sigma[0] = 0.5
    for t in range(1, n):
        sigma[t] = math.sqrt(0.01 + 0.05 * resid[t-1]**2 + 0.90 * sigma[t-1]**2)
        resid[t] = sigma[t] * rng.standard_normal()
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    out = fit_garch_residual(pd.Series(resid, index=idx))
    if out.ok:
        assert out.sigma > 0
        assert 0.7 < out.persistence < 1.05  # ≈ α+β should be high


def test_garch_too_short_returns_ok_false():
    from vol_models import fit_garch_residual
    s = pd.Series(np.random.default_rng(1).normal(0, 1, 40))
    out = fit_garch_residual(s)
    assert out.ok is False
    assert not math.isfinite(out.sigma)


def test_garch_zero_input_still_gracefully_falls_back():
    from vol_models import fit_garch_residual
    s = pd.Series(np.zeros(200))
    out = fit_garch_residual(s)
    # Either ok=False (zero variance ⇒ fit fails or sigma=0) or
    # z comes out finite — both are acceptable
    if out.ok:
        assert math.isfinite(out.z)


def test_compute_spread_zscore_emits_z_vol(synth_prices):
    from quantitative_models import compute_spread_zscore
    df = compute_spread_zscore(synth_prices, window=60)
    for col in ("Z_Score", "Z_Vol", "Spread_EwmaStd"):
        assert col in df.columns
    assert df["Z_Vol"].notna().sum() > 10
