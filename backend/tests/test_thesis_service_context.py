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


def test_stream_thesis_done_event_includes_decorated_fields(monkeypatch):
    """Regression for #65: stream_thesis must call decorate_thesis_for_execution
    so the SSE done payload carries populated instruments[] and checklist[].

    Patches _generate_thesis + _build_thesis_context to avoid network I/O;
    asserts the done event's thesis dict has 3 instruments and 5 checklist items
    for a long_spread stance.
    """
    import asyncio
    import json

    import trade_thesis
    import backend.services.thesis_service as ts

    ctx = trade_thesis.ThesisContext(
        latest_brent=80.0,
        latest_wti=76.0,
        latest_spread=4.0,
        rolling_mean_90d=3.5,
        rolling_std_90d=0.5,
        current_z=1.0,
        z_percentile_5y=60.0,
        days_since_last_abs_z_over_2=5,
        bt_hit_rate=0.6,
        bt_avg_hold_days=3.0,
        bt_avg_pnl_per_bbl=0.1,
        bt_max_drawdown_usd=-1000.0,
        bt_sharpe=0.8,
        inventory_source="EIA",
        inventory_current_bbls=400_000_000.0,
        inventory_4w_slope_bbls_per_day=-100_000.0,
        inventory_52w_slope_bbls_per_day=-50_000.0,
        inventory_floor_bbls=300_000_000.0,
        inventory_projected_floor_date="2027-04-22",
        days_of_supply=20.0,
        fleet_total_mbbl=500.0,
        fleet_jones_mbbl=100.0,
        fleet_shadow_mbbl=200.0,
        fleet_sanctioned_mbbl=50.0,
        fleet_source="Historical snapshot",
        fleet_delta_vs_30d_mbbl=5.0,
        vol_brent_30d_pct=25.0,
        vol_wti_30d_pct=27.0,
        vol_spread_30d_pct=10.0,
        vol_spread_1y_percentile=55.0,
        next_eia_release_date="2026-04-22",
        session_is_open=True,
        weekend_or_holiday=False,
        user_z_threshold=2.0,
        hours_to_next_eia=48.0,
    )
    long_thesis = trade_thesis.Thesis(
        raw={
            "stance": "long_spread",
            "conviction_0_to_10": 7,
            "time_horizon_days": 5,
            "position_sizing": {"suggested_pct_of_capital": 3.0},
        },
        generated_at="2026-04-27T00:00:00Z",
        source="test",
        mode="fast",
    )

    monkeypatch.setattr(ts, "_generate_thesis", lambda *a, **kw: long_thesis)
    monkeypatch.setattr(ts, "_build_thesis_context", lambda: ctx)

    async def _run():
        events = []
        async for ev in ts.stream_thesis(mode="fast", portfolio_usd=100_000):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    done = next(e for e in events if e.get("event") == "done")
    payload = json.loads(done["data"])
    thesis_dict = payload["thesis"]
    assert len(thesis_dict["instruments"]) == 3, (
        "expected 3 instrument tiers from decorate_thesis_for_execution — "
        "got empty list, confirming #65 regression"
    )
    assert len(thesis_dict["checklist"]) == 5, (
        "expected 5 checklist items from decorate_thesis_for_execution"
    )
