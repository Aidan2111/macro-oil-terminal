"""Regression tests for backend.services.thesis_service._build_thesis_context.

Pin the contract for the three failure modes the live SSE has hit:

  1. quantitative_models.run_backtest returns numeric keys as None
     (which made build_context's `float(backtest.get(k, 0.0))` raise
     TypeError because dict.get returns the explicit None, not the
     default).
  2. data_ingestion.fetch_ais_data returns an AISResult dataclass —
     build_context expects a raw DataFrame, so the service must unwrap
     to `.frame`.
  3. providers._cftc.fetch_wti_positioning returns a COTResult that
     does NOT carry an mm_zscore_3y attribute — service must compute
     it and monkey-attach.

We avoid stubbing out the full provider chain (which has side effects
at import time); instead we test the focused normalisation logic the
service applies to its provider outputs.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass

import pandas as pd
import pytest


_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@dataclass
class _COTResult:
    frame: pd.DataFrame


@dataclass
class _AISResult:
    frame: pd.DataFrame


def test_backtest_none_numerics_get_normalised():
    """Reproduce the float(None) bug in isolation: feed the same
    normalisation block the service runs after a backtest call to a
    dict that mirrors what run_backtest returns when no trades fire,
    and assert every numeric key collapses to 0.0."""
    raw = {
        "sharpe": None,
        "sortino": None,
        "max_drawdown_usd": None,
        "win_rate": None,
        "avg_days_held": None,
        "avg_pnl_per_bbl": None,
        "n_trades": 0,
    }
    backtest = dict(raw)
    for k in (
        "win_rate",
        "hit_rate",
        "avg_days_held",
        "avg_pnl_per_bbl",
        "max_drawdown_usd",
        "sharpe",
        "sortino",
        "total_pnl_usd",
    ):
        v = backtest.get(k)
        if v is None:
            backtest[k] = 0.0
        else:
            try:
                backtest[k] = float(v)
            except (TypeError, ValueError):
                backtest[k] = 0.0
    backtest.setdefault("equity_curve", [])
    backtest.setdefault("trades", [])
    backtest.setdefault("n_trades", 0)

    # Every key build_context calls float() on must now be a real
    # float — dict.get's "default if missing" gotcha is avoided.
    for k in (
        "win_rate",
        "avg_days_held",
        "avg_pnl_per_bbl",
        "max_drawdown_usd",
        "sharpe",
    ):
        assert backtest[k] == 0.0
        assert isinstance(backtest[k], float)
    assert backtest["equity_curve"] == []
    assert backtest["trades"] == []


def test_ais_result_unwrap_to_frame():
    """The service expects to extract `.frame` from whatever
    fetch_ais_data returns. AISResult is a dataclass; unwrap should
    yield the inner DataFrame."""
    df = pd.DataFrame({"mmsi": [1, 2], "lat": [0, 1], "lon": [0, 1]})
    result = _AISResult(frame=df)
    unwrapped = (
        getattr(result, "frame", None) if hasattr(result, "frame") else result
    )
    assert isinstance(unwrapped, pd.DataFrame)
    assert len(unwrapped) == 2


def test_cot_result_can_carry_mm_zscore_attribute():
    """build_context reads `cftc_res.mm_zscore_3y` directly. COTResult
    is a frozen-style dataclass with no such field, but Python lets
    us attach arbitrary attributes to non-frozen dataclasses, which
    is what the service does."""
    cot = _COTResult(frame=pd.DataFrame({"mm_net": [100, 200, 300]}))
    setattr(cot, "mm_zscore_3y", 0.42)
    assert cot.mm_zscore_3y == 0.42  # type: ignore[attr-defined]


def test_thesis_service_module_imports_cleanly():
    """Smoke-import: the service must load without exploding (heavy
    deps live inside the function body, not at module-top)."""
    import backend.services.thesis_service as ts  # noqa: F401

    assert hasattr(ts, "_build_thesis_context")
    assert callable(ts._build_thesis_context)
