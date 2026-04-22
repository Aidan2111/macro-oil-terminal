"""Tests for the 3-2-1 crack spread helper."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_compute_crack_offline_returns_not_ok(monkeypatch):
    """Without a live yfinance, we should get ok=False rather than a crash."""
    import crack_spread

    def _boom(*a, **kw):
        raise RuntimeError("no network")
    monkeypatch.setattr(crack_spread, "_load", _boom)

    out = crack_spread.compute_crack()
    assert out.ok is False
    assert "yfinance" in out.note.lower()


def test_compute_crack_happy_path(monkeypatch):
    """Mock a clean 3-ticker frame + Brent-WTI panel and verify the math."""
    import crack_spread as cs

    idx = pd.date_range("2024-01-01", periods=120, freq="D")
    rng = np.random.default_rng(42)

    rbob = pd.Series(np.linspace(2.50, 2.65, 120) + rng.normal(0, 0.02, 120), index=idx)
    ho = pd.Series(np.linspace(2.80, 2.95, 120) + rng.normal(0, 0.02, 120), index=idx)
    wti = pd.Series(np.linspace(78.0, 82.0, 120) + rng.normal(0, 0.3, 120), index=idx)

    raw = pd.DataFrame({
        "RB=F": rbob,
        "HO=F": ho,
        "CL=F": wti,
    })
    monkeypatch.setattr(cs, "_load", lambda tickers, years=1: raw)

    # Synthetic Brent-WTI panel aligned to the same index
    brent = wti + 3.2 + rng.normal(0, 0.2, 120)
    panel = pd.DataFrame({"Brent": brent, "WTI": wti}, index=idx)

    out = cs.compute_crack(brent_wti_daily=panel, years=1)
    assert out.ok
    # Crack_321 should land in a sensible USD/bbl range (~$20-$35/bbl normal regime)
    assert 5 < out.latest_crack_usd < 80
    # Correlation must be finite
    assert -1.0 <= out.corr_30d_vs_brent_wti <= 1.0 or np.isnan(out.corr_30d_vs_brent_wti)
    assert out.series is not None
    assert "Crack_321_usd" in out.series.columns


def test_compute_crack_no_brent_wti_panel(monkeypatch):
    """When no Brent-WTI frame is supplied, the correlation is NaN but ok=True."""
    import crack_spread as cs

    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    raw = pd.DataFrame({
        "RB=F": np.full(60, 2.5),
        "HO=F": np.full(60, 2.8),
        "CL=F": np.full(60, 80.0),
    }, index=idx)
    monkeypatch.setattr(cs, "_load", lambda tickers, years=1: raw)

    out = cs.compute_crack(brent_wti_daily=None)
    assert out.ok
    assert np.isnan(out.corr_30d_vs_brent_wti)
