"""Issue #105 — Databento provider unit tests.

Acceptance:
  * /api/spread serves Databento prices when DATABENTO_API_KEY is set
    (verified via the orchestrator's source label).
  * yfinance fallback path tested with the env var unset.
  * Code path handles missing-key gracefully.
"""

from __future__ import annotations

import os
import sys
import pathlib
from datetime import datetime, timezone

import pandas as pd
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_databento_module_raises_when_key_unset(monkeypatch):
    """Without DATABENTO_API_KEY the module must raise — caller falls
    through to yfinance."""
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    from providers import _databento

    with pytest.raises(RuntimeError, match="DATABENTO_API_KEY"):
        _databento.fetch_intraday()


def test_databento_module_raises_when_sdk_missing(monkeypatch):
    """Even with the key set, an unimportable SDK must raise."""
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "databento", None)
    from providers import _databento

    with pytest.raises(RuntimeError, match="databento SDK not installed"):
        _databento.fetch_daily()


def test_active_pricing_provider_reflects_databento_key(monkeypatch):
    """active_pricing_provider() must surface the Databento label
    when the key is set."""
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    from providers import pricing

    label = pricing.active_pricing_provider("intraday")
    assert "Databento" in label


def test_active_pricing_provider_fallback_label_without_key(monkeypatch):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    from providers import pricing

    label = pricing.active_pricing_provider("intraday")
    assert "Yahoo Finance" in label


def test_orchestrator_falls_through_to_yfinance_when_databento_errors(monkeypatch):
    """Set DATABENTO_API_KEY, make _databento.fetch_daily raise, and
    confirm pricing.fetch_pricing_daily falls through to yfinance."""
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")

    import providers.pricing as pricing
    import providers._databento as databento_mod
    import providers._yfinance as yf_mod

    fake_frame = pd.DataFrame(
        {"Brent": [100.0], "WTI": [95.0], "Spread": [5.0]},
        index=pd.to_datetime(["2026-04-01"]),
    )
    fake_frame.index.name = "Date"

    def _databento_raises(*args, **kwargs):
        raise RuntimeError("databento: pretend SDK transient failure")

    def _yfinance_ok(*args, **kwargs):
        return fake_frame

    monkeypatch.setattr(databento_mod, "fetch_daily", _databento_raises)
    monkeypatch.setattr(yf_mod, "fetch_daily", _yfinance_ok)

    out = pricing.fetch_pricing_daily(years=1)
    assert out.source == "yfinance"
    assert out.frame is fake_frame


def test_orchestrator_uses_databento_when_keyed_and_provider_succeeds(monkeypatch):
    """Happy path — when Databento returns a frame the orchestrator
    must report source='databento'."""
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")

    import providers.pricing as pricing
    import providers._databento as databento_mod

    fake_frame = pd.DataFrame(
        {"Brent": [101.0], "WTI": [96.0], "Spread": [5.0]},
        index=pd.to_datetime(["2026-04-01"]),
    )
    fake_frame.index.name = "Date"

    monkeypatch.setattr(databento_mod, "fetch_daily", lambda **kw: fake_frame)

    out = pricing.fetch_pricing_daily(years=1)
    assert out.source == "databento"
    assert out.frame is fake_frame
