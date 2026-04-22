"""Wire-level tests for CFTC through data_ingestion + thesis_context."""

from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def stub_cftc_frame():
    idx = pd.date_range("2024-01-02", periods=30, freq="W-TUE")
    return pd.DataFrame(
        {
            "mm_net": [100_000 + i * 1500 for i in range(30)],
            "producer_net": [250_000 - i * 1000 for i in range(30)],
            "swap_net": [-400_000 + i * 500 for i in range(30)],
            "other_rept_net": [100_000 for _ in range(30)],
            "nonrept_net": [30_000 for _ in range(30)],
            "open_interest": [2_000_000 for _ in range(30)],
            "market": ["WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"] * 30,
        },
        index=idx,
    )


def test_fetch_cftc_positioning_passes_through(monkeypatch, stub_cftc_frame):
    """data_ingestion.fetch_cftc_positioning should wrap provider result + Z-score."""
    import data_ingestion as di

    class _StubR:
        frame = stub_cftc_frame
        source_url = "https://example.com/zip"
        fetched_at = pd.Timestamp.utcnow()
        market_name = "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"
        weeks = len(stub_cftc_frame)

    monkeypatch.setattr(di._cftc_provider, "fetch_wti_positioning", lambda *a, **kw: _StubR())
    monkeypatch.setattr(di._cftc_provider, "managed_money_zscore", lambda *a, **kw: 1.25)

    r = di.fetch_cftc_positioning()
    assert r.weeks == len(stub_cftc_frame)
    assert r.mm_zscore_3y == 1.25
    assert "CFTC" in r.source
    assert "WTI" in r.source


def test_build_context_populates_cftc_fields(stub_cftc_frame):
    """build_context should propagate CFTC fields to the ThesisContext payload."""
    from thesis_context import build_context
    from data_ingestion import COTResult

    # Minimal stubs for the other required kwargs
    class _PricingRes:
        frame = pd.DataFrame(
            {"Brent": [80.0] * 60, "WTI": [77.0] * 60},
            index=pd.date_range("2024-01-01", periods=60, freq="D"),
        )
        source = "stub"
        fetched_at = pd.Timestamp.utcnow()

    class _InvRes:
        frame = pd.DataFrame(
            {
                "Commercial_bbls": [400_000_000.0] * 30,
                "SPR_bbls": [370_000_000.0] * 30,
                "Cushing_bbls": [30_000_000.0] * 30,
                "Total_Inventory_bbls": [770_000_000.0] * 30,
            },
            index=pd.date_range("2024-01-02", periods=30, freq="W"),
        )
        source = "EIA"
        source_url = "https://example.com"
        fetched_at = pd.Timestamp.utcnow()

    spread_df = pd.DataFrame(
        {
            "Spread": [3.0] * 60,
            "Spread_Mean": [3.0] * 60,
            "Spread_Std": [0.8] * 60,
            "Z_Score": [0.1] * 60,
        },
        index=pd.date_range("2024-01-01", periods=60, freq="D"),
    )
    backtest = {
        "win_rate": 0.5, "avg_days_held": 5, "avg_pnl_per_bbl": 0.2,
        "max_drawdown_usd": 1000, "sharpe": 0.8,
    }
    depletion = {"projected_floor_date": None}
    ais_agg = pd.DataFrame({"Category": [], "Total_Cargo_Mbbl": []})
    ais_with_cat = pd.DataFrame({"Cargo_Volume_bbls": [1_400_000] * 10})

    cftc = COTResult(
        frame=stub_cftc_frame,
        source="CFTC disaggregated futures",
        source_url="https://example.com/zip",
        fetched_at=pd.Timestamp.utcnow(),
        market_name="WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
        weeks=len(stub_cftc_frame),
        mm_zscore_3y=0.75,
    )

    ctx = build_context(
        pricing_res=_PricingRes(),
        inventory_res=_InvRes(),
        spread_df=spread_df,
        backtest=backtest,
        depletion=depletion,
        ais_agg=ais_agg,
        ais_with_cat=ais_with_cat,
        z_threshold=2.0,
        floor_bbls=350_000_000.0,
        cftc_res=cftc,
    )
    assert ctx.cftc_as_of_date is not None
    assert ctx.cftc_mm_net == int(stub_cftc_frame["mm_net"].iloc[-1])
    assert ctx.cftc_producer_net == int(stub_cftc_frame["producer_net"].iloc[-1])
    assert ctx.cftc_swap_net == int(stub_cftc_frame["swap_net"].iloc[-1])
    assert ctx.cftc_open_interest == 2_000_000
    assert ctx.cftc_mm_zscore_3y == pytest.approx(0.75)
    assert 0.0 <= ctx.cftc_mm_pctile_3y <= 100.0


def test_build_context_handles_missing_cftc():
    """When cftc_res is None the thesis context still builds with nulls."""
    from thesis_context import build_context

    class _PricingRes:
        frame = pd.DataFrame(
            {"Brent": [80.0] * 60, "WTI": [77.0] * 60},
            index=pd.date_range("2024-01-01", periods=60, freq="D"),
        )
        source = "stub"
        fetched_at = pd.Timestamp.utcnow()

    class _InvRes:
        frame = pd.DataFrame(
            {
                "Commercial_bbls": [400_000_000.0] * 5,
                "SPR_bbls": [370_000_000.0] * 5,
                "Cushing_bbls": [30_000_000.0] * 5,
                "Total_Inventory_bbls": [770_000_000.0] * 5,
            },
            index=pd.date_range("2024-01-02", periods=5, freq="W"),
        )
        source = "EIA"
        source_url = "https://example.com"
        fetched_at = pd.Timestamp.utcnow()

    spread_df = pd.DataFrame(
        {
            "Spread": [3.0] * 60,
            "Spread_Mean": [3.0] * 60,
            "Spread_Std": [0.8] * 60,
            "Z_Score": [0.1] * 60,
        },
        index=pd.date_range("2024-01-01", periods=60, freq="D"),
    )
    backtest = {"win_rate": 0, "avg_days_held": 0, "avg_pnl_per_bbl": 0, "max_drawdown_usd": 0, "sharpe": 0}
    depletion = {"projected_floor_date": None}
    ais_agg = pd.DataFrame({"Category": [], "Total_Cargo_Mbbl": []})
    ais_with_cat = pd.DataFrame({"Cargo_Volume_bbls": []})

    ctx = build_context(
        pricing_res=_PricingRes(),
        inventory_res=_InvRes(),
        spread_df=spread_df,
        backtest=backtest,
        depletion=depletion,
        ais_agg=ais_agg,
        ais_with_cat=ais_with_cat,
        z_threshold=2.0,
        floor_bbls=350_000_000.0,
        cftc_res=None,
    )
    assert ctx.cftc_as_of_date is None
    assert ctx.cftc_mm_net is None
    assert ctx.cftc_mm_zscore_3y is None
