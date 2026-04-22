"""Shared pytest fixtures for the macro-oil-terminal unit suite.

Offline by design: every data-provider test uses the checked-in EIA
fixture under ``tests/fixtures/``. Tests never touch yfinance or
Azure OpenAI unless explicitly marked ``live_llm`` or ``network``.
"""

from __future__ import annotations

import os
import pathlib
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest


# Make the project importable when pytest is invoked from the repo root.
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch):
    """Prevent accidental live LLM calls in unit tests.

    Every test starts with Azure OpenAI env vars stripped. Tests marked
    ``live_llm`` opt in explicitly by setting them inside the test.
    """
    for key in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_KEY",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_API_VERSION_REASONING",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_DEPLOYMENT_FAST",
        "AZURE_OPENAI_DEPLOYMENT_DEEP",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def eia_fixture(monkeypatch):
    """Monkey-patch requests.get used by providers._eia to serve fixtures."""
    fixtures_dir = pathlib.Path(__file__).parent / "fixtures"
    import requests as _requests
    original = _requests.get

    def _patched(url, *args, **kwargs):
        class _R:
            def __init__(self, text):
                self.text = text
                self.status_code = 200
            def raise_for_status(self):
                pass

        if "WCESTUS1" in url:
            return _R((fixtures_dir / "eia_WCESTUS1.html").read_text())
        if "WCSSTUS1" in url:
            return _R((fixtures_dir / "eia_WCSSTUS1.html").read_text())
        return original(url, *args, **kwargs)

    monkeypatch.setattr(_requests, "get", _patched)


@pytest.fixture
def synth_prices() -> pd.DataFrame:
    """Deterministic synthetic 400-day Brent/WTI frame for math tests."""
    idx = pd.date_range("2024-01-01", periods=400, freq="D")
    rng = np.random.default_rng(42)
    wti = np.cumsum(rng.normal(0, 0.5, 400)) + 75.0
    brent = wti + 3.2 + np.cumsum(rng.normal(0, 0.07, 400))
    return pd.DataFrame({"Brent": brent, "WTI": wti}, index=idx)


@pytest.fixture
def spread_with_zscore(synth_prices):
    from quantitative_models import compute_spread_zscore
    return compute_spread_zscore(synth_prices, window=90)


@pytest.fixture
def sample_backtest(spread_with_zscore):
    from quantitative_models import backtest_zscore_meanreversion
    return backtest_zscore_meanreversion(spread_with_zscore, entry_z=1.0, exit_z=0.2)


@pytest.fixture
def sample_ctx():
    """A realistic-ish ThesisContext for downstream tests."""
    from trade_thesis import ThesisContext
    return ThesisContext(
        latest_brent=82.10, latest_wti=78.40, latest_spread=3.70,
        rolling_mean_90d=3.2, rolling_std_90d=0.7,
        current_z=2.3, z_percentile_5y=91.0, days_since_last_abs_z_over_2=40,
        bt_hit_rate=0.68, bt_avg_hold_days=30.0, bt_avg_pnl_per_bbl=1.2,
        bt_max_drawdown_usd=-4000.0, bt_sharpe=1.6,
        inventory_source="EIA", inventory_current_bbls=870e6,
        inventory_4w_slope_bbls_per_day=-350_000.0,
        inventory_52w_slope_bbls_per_day=-95_000.0,
        inventory_floor_bbls=300e6,
        inventory_projected_floor_date="2028-06-15",
        days_of_supply=None,
        fleet_total_mbbl=640.0, fleet_jones_mbbl=120.0,
        fleet_shadow_mbbl=260.0, fleet_sanctioned_mbbl=180.0,
        fleet_source="Historical snapshot", fleet_delta_vs_30d_mbbl=None,
        vol_brent_30d_pct=28.0, vol_wti_30d_pct=29.0,
        vol_spread_30d_pct=12.0, vol_spread_1y_percentile=55.0,
        next_eia_release_date="2026-04-22", session_is_open=True,
        weekend_or_holiday=False, user_z_threshold=2.0,
    )
