"""TDD tests for the hero-thesis decoration layer (Tasks 2-5/6)."""

from trade_thesis import Instrument, ChecklistItem


def test_instrument_dataclass_has_expected_fields():
    inst = Instrument(
        tier=1,
        name="Paper",
        symbol=None,
        rationale="track only",
        suggested_size_pct=0.0,
        worst_case_per_unit="N/A",
    )
    assert inst.tier == 1
    assert inst.name == "Paper"
    assert inst.symbol is None
    assert inst.rationale == "track only"
    assert inst.suggested_size_pct == 0.0
    assert inst.worst_case_per_unit == "N/A"


def test_checklist_item_dataclass_has_expected_fields():
    item = ChecklistItem(
        key="stop_in_place",
        prompt="I have a stop in place.",
        auto_check=None,
    )
    assert item.key == "stop_in_place"
    assert item.prompt == "I have a stop in place."
    assert item.auto_check is None


import pytest

from trade_thesis import Thesis, ThesisContext, decorate_thesis_for_execution


@pytest.fixture
def minimal_context():
    return ThesisContext(
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


def _thesis(**raw_overrides) -> Thesis:
    """Helper: build a minimal Thesis with a stub raw dict."""
    raw = {
        "stance": "flat",
        "conviction_0_to_10": 0.0,
        "time_horizon_days": 0,
        "position_sizing": {"suggested_pct_of_capital": 0.0},
    }
    raw.update(raw_overrides)
    return Thesis(
        raw=raw,
        generated_at="2026-04-22T00:00:00Z",
        source="rule-based (fixture)",
        mode="rule-based",
    )


def test_decorate_flat_thesis_returns_empty_instruments_and_checklist(minimal_context):
    thesis = _thesis(stance="flat")
    out = decorate_thesis_for_execution(thesis, minimal_context)
    assert out.instruments == []
    assert out.checklist == []


def test_decorate_does_not_mutate_input_thesis(minimal_context):
    thesis = _thesis(stance="flat")
    before_instruments_id = id(thesis.instruments)
    _ = decorate_thesis_for_execution(thesis, minimal_context)
    # input is untouched — same list object, still empty
    assert thesis.instruments == []
    assert id(thesis.instruments) == before_instruments_id


def test_decorate_returns_a_deepcopy_not_the_same_object(minimal_context):
    thesis = _thesis(stance="flat")
    out = decorate_thesis_for_execution(thesis, minimal_context)
    assert out is not thesis
