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
