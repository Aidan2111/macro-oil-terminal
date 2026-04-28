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


def test_decorate_long_spread_produces_three_tiers(minimal_context):
    thesis = _thesis(
        stance="long_spread",
        conviction_0_to_10=7.0,
        time_horizon_days=4,
        position_sizing={"suggested_pct_of_capital": 4.0,
                         "method": "fixed_fractional", "rationale": "stub"},
    )
    out = decorate_thesis_for_execution(thesis, minimal_context)
    assert [i.tier for i in out.instruments] == [1, 2, 3]
    # Paper tier is always zero size
    assert out.instruments[0].suggested_size_pct == 0.0
    assert out.instruments[0].symbol is None
    # ETF at half the thesis suggested size
    assert out.instruments[1].suggested_size_pct == pytest.approx(2.0)
    assert "USO" in out.instruments[1].rationale
    assert "BNO" in out.instruments[1].rationale
    assert "long uso" in out.instruments[1].rationale.lower()
    # Futures at full suggested size
    assert out.instruments[2].suggested_size_pct == pytest.approx(4.0)
    assert "CL=F" in out.instruments[2].rationale or "CL" in out.instruments[2].rationale
    # Checklist is populated in Task 5 (length asserted here; order asserted below)
    assert len(out.checklist) == 5


def test_decorate_short_spread_inverts_etf_pair(minimal_context):
    thesis = _thesis(
        stance="short_spread",
        conviction_0_to_10=7.0,
        time_horizon_days=4,
        position_sizing={"suggested_pct_of_capital": 4.0,
                         "method": "fixed_fractional", "rationale": "stub"},
    )
    out = decorate_thesis_for_execution(thesis, minimal_context)
    # ETF leg inverted: short USO / long BNO
    assert "short uso" in out.instruments[1].rationale.lower()
    assert "long bno" in out.instruments[1].rationale.lower()
    # Futures leg inverted
    assert "short CL=F" in out.instruments[2].rationale or "short CL" in out.instruments[2].rationale.lower()


def test_decorate_tier3_size_tracks_thesis_suggested_pct(minimal_context):
    """Tier 3 (futures) size must equal the thesis suggested_pct_of_capital —
    the guardrail clamp lives upstream and is NOT re-applied here."""
    thesis = _thesis(
        stance="long_spread",
        conviction_0_to_10=6.0,
        time_horizon_days=4,
        position_sizing={"suggested_pct_of_capital": 8.5,
                         "method": "fixed_fractional", "rationale": "stub"},
    )
    out = decorate_thesis_for_execution(thesis, minimal_context)
    assert out.instruments[2].suggested_size_pct == pytest.approx(8.5)
    assert out.instruments[1].suggested_size_pct == pytest.approx(4.25)


def test_decorate_flat_stance_still_empty_instruments(minimal_context):
    """Regression: Task 3 behaviour preserved."""
    thesis = _thesis(stance="flat")
    out = decorate_thesis_for_execution(thesis, minimal_context)
    assert out.instruments == []
    assert out.checklist == []


def test_decorate_checklist_has_five_items_in_order(minimal_context):
    thesis = _thesis(
        stance="long_spread",
        conviction_0_to_10=7.0,
        time_horizon_days=4,
        position_sizing={"suggested_pct_of_capital": 4.0,
                         "method": "fixed_fractional", "rationale": "stub"},
    )
    out = decorate_thesis_for_execution(thesis, minimal_context)
    assert [c.key for c in out.checklist] == [
        "stop_in_place",
        "vol_clamp_ok",
        "half_life_ack",
        "catalyst_clear",
        "no_conflicting_recent_thesis",
    ]


def test_decorate_checklist_auto_checks_vol_clamp_when_vol_below_p85(minimal_context):
    # minimal_context has vol_spread_1y_percentile=55 < 85 -> auto-check True
    thesis = _thesis(
        stance="long_spread",
        conviction_0_to_10=7.0,
        time_horizon_days=4,
        position_sizing={"suggested_pct_of_capital": 4.0,
                         "method": "fixed_fractional", "rationale": "stub"},
    )
    out = decorate_thesis_for_execution(thesis, minimal_context)
    vol_item = next(c for c in out.checklist if c.key == "vol_clamp_ok")
    assert vol_item.auto_check is True


def test_decorate_checklist_vol_clamp_false_when_vol_over_p85(minimal_context):
    from dataclasses import replace
    hot_ctx = replace(minimal_context, vol_spread_1y_percentile=92.0)
    thesis = _thesis(stance="long_spread",
                     position_sizing={"suggested_pct_of_capital": 4.0,
                                      "method": "fixed_fractional", "rationale": "stub"})
    out = decorate_thesis_for_execution(thesis, hot_ctx)
    vol_item = next(c for c in out.checklist if c.key == "vol_clamp_ok")
    assert vol_item.auto_check is False


def test_decorate_checklist_catalyst_clear_over_24h(minimal_context):
    # minimal_context has hours_to_next_eia=48 -> auto-check True
    thesis = _thesis(stance="long_spread",
                     position_sizing={"suggested_pct_of_capital": 4.0,
                                      "method": "fixed_fractional", "rationale": "stub"})
    out = decorate_thesis_for_execution(thesis, minimal_context)
    cat_item = next(c for c in out.checklist if c.key == "catalyst_clear")
    assert cat_item.auto_check is True


def test_decorate_checklist_catalyst_false_when_eia_under_24h(minimal_context):
    from dataclasses import replace
    close_ctx = replace(minimal_context, hours_to_next_eia=6.0)
    thesis = _thesis(stance="long_spread",
                     position_sizing={"suggested_pct_of_capital": 4.0,
                                      "method": "fixed_fractional", "rationale": "stub"})
    out = decorate_thesis_for_execution(thesis, close_ctx)
    cat_item = next(c for c in out.checklist if c.key == "catalyst_clear")
    assert cat_item.auto_check is False


def test_decorate_checklist_catalyst_none_when_hours_unknown(minimal_context):
    from dataclasses import replace
    unknown_ctx = replace(minimal_context, hours_to_next_eia=None)
    thesis = _thesis(stance="long_spread",
                     position_sizing={"suggested_pct_of_capital": 4.0,
                                      "method": "fixed_fractional", "rationale": "stub"})
    out = decorate_thesis_for_execution(thesis, unknown_ctx)
    cat_item = next(c for c in out.checklist if c.key == "catalyst_clear")
    assert cat_item.auto_check is None


def test_decorate_checklist_user_items_always_none(minimal_context):
    thesis = _thesis(stance="long_spread",
                     position_sizing={"suggested_pct_of_capital": 4.0,
                                      "method": "fixed_fractional", "rationale": "stub"})
    out = decorate_thesis_for_execution(thesis, minimal_context)
    by_key = {c.key: c for c in out.checklist}
    assert by_key["stop_in_place"].auto_check is None
    assert by_key["half_life_ack"].auto_check is None
    assert by_key["no_conflicting_recent_thesis"].auto_check is None


def test_decorate_flat_stance_still_empty_checklist(minimal_context):
    thesis = _thesis(stance="flat")
    out = decorate_thesis_for_execution(thesis, minimal_context)
    assert out.checklist == []


# ---------------------------------------------------------------------------
# Audit log persistence — instruments + checklist must be round-tripped so
# the cached `/api/thesis/latest` first paint matches what the SSE regen
# would yield. Without this, the hero rendered the cached stance + headline
# but no trade tickets / checklist for ~100s on every page load while the
# live regen stream completed.
# ---------------------------------------------------------------------------


def test_append_audit_persists_decorated_instruments_and_checklist(
    monkeypatch, tmp_path, minimal_context
):
    """Issue #65 follow-up — `_append_audit` must persist
    `thesis.instruments` and `thesis.checklist` (the decoration output)
    so /api/thesis/latest returns them on first paint."""
    import json
    import pathlib

    import trade_thesis as tt

    # Re-route the audit path into a temp file so the test doesn't
    # spew into the live data/trade_theses.jsonl.
    audit_path = pathlib.Path(tmp_path / "trade_theses.jsonl")
    monkeypatch.setattr(tt, "_AUDIT_PATH", audit_path)

    # Build a long-spread thesis so decoration produces 3 instruments
    # and 5 checklist items.
    thesis = _thesis(
        stance="long_spread",
        position_sizing={
            "suggested_pct_of_capital": 1.0,
            "method": "fixed_fractional",
            "rationale": "stub",
        },
    )
    thesis = decorate_thesis_for_execution(thesis, minimal_context)
    assert len(thesis.instruments) == 3
    assert len(thesis.checklist) == 5

    tt._append_audit(minimal_context, thesis)

    rows = audit_path.read_text().strip().splitlines()
    assert len(rows) == 1
    record = json.loads(rows[0])

    # Instruments and checklist must be present, non-empty, and have
    # the same shape the frontend expects (dict-of-fields per item).
    assert record["instruments"], "instruments missing from audit log"
    assert len(record["instruments"]) == 3
    assert all(isinstance(i, dict) and "tier" in i for i in record["instruments"])

    assert record["checklist"], "checklist missing from audit log"
    assert len(record["checklist"]) == 5
    assert all(
        isinstance(c, dict) and "key" in c and "prompt" in c
        for c in record["checklist"]
    )


def test_append_audit_flat_thesis_writes_empty_arrays(
    monkeypatch, tmp_path, minimal_context
):
    """A flat stance has no instruments / checklist — the audit row
    should still contain the keys (as empty lists) so the frontend
    parser sees a known-shape record."""
    import json
    import pathlib

    import trade_thesis as tt

    audit_path = pathlib.Path(tmp_path / "trade_theses.jsonl")
    monkeypatch.setattr(tt, "_AUDIT_PATH", audit_path)

    thesis = _thesis(stance="flat")
    thesis = decorate_thesis_for_execution(thesis, minimal_context)
    tt._append_audit(minimal_context, thesis)

    record = json.loads(audit_path.read_text().strip())
    assert record["instruments"] == []
    assert record["checklist"] == []
