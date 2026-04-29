"""Unit tests for the OFAC SDN sanctions delta tracker (issue #81)."""

from __future__ import annotations

import pathlib
import pytest


_FAKE_SDN_PREV = """1001,"NIOC IRAN PETROLEUM","Entity","[IRAN]","Tehran",,,,
1002,"PDVSA VENEZUELA","Entity","[VENEZUELA]","Caracas",,,,
"""

_FAKE_SDN_CUR = """1001,"NIOC IRAN PETROLEUM","Entity","[IRAN]","Tehran",,,,
1002,"PDVSA VENEZUELA","Entity","[VENEZUELA]","Caracas",,,,
1003,"GAZPROM TRADING","Entity","[RUSSIA]","Moscow",,,,
1004,"IRGC SHIPPING","Entity","[IRAN]","Bandar Abbas",,,,
1005,"BLAH NORTH KOREA","Entity","[DPRK]","Pyongyang",,,,
"""


def test_classify_row_picks_each_region():
    from providers import ofac

    iran_row = ["1001", "NIOC IRAN PETROLEUM", "Entity", "[IRAN]"]
    rus_row = ["1002", "GAZPROM TRADING", "Entity", "[RUSSIA]"]
    ven_row = ["1003", "PDVSA VENEZUELA", "Entity", "[VENEZUELA]"]
    irrelevant = ["1004", "BLAH NORTH KOREA", "Entity", "[DPRK]"]

    assert ofac.classify_row(iran_row) == {"iran"}
    assert ofac.classify_row(rus_row) == {"russia"}
    assert ofac.classify_row(ven_row) == {"venezuela"}
    assert ofac.classify_row(irrelevant) == set()


def test_bucket_counts_dedupes_by_sdn_id():
    from providers import ofac

    rows = [
        ["1001", "NIOC IRAN PETROLEUM", "Entity", "[IRAN]"],
        ["1001", "NIOC IRAN PETROLEUM (DUPLICATE)", "Entity", "[IRAN]"],
        ["1002", "GAZPROM", "Entity", "[RUSSIA]"],
    ]
    counts = ofac.bucket_counts(rows)
    assert counts["iran"] == 1
    assert counts["russia"] == 1
    assert counts["venezuela"] == 0


def test_compute_delta_no_prior_snapshot(monkeypatch, tmp_path):
    """First-ever fetch — no previous snapshot, so the delta equals
    the full count and no additions show up (we only diff vs prev)."""
    from providers import ofac

    monkeypatch.setattr(ofac, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(ofac, "SDN_PATH", tmp_path / "sdn.csv")
    monkeypatch.setattr(ofac, "SDN_PREV_PATH", tmp_path / "sdn-prev.csv")

    def _fake_get(url: str, *, timeout: float = 30.0) -> bytes:
        return _FAKE_SDN_CUR.encode("utf-8")

    monkeypatch.setattr(ofac, "_http_get", _fake_get)

    payload = ofac.compute_delta()
    assert payload["totals"]["iran"] == 2  # NIOC + IRGC
    assert payload["totals"]["russia"] == 1
    assert payload["totals"]["venezuela"] == 1
    # No prior snapshot → delta equals full counts
    assert payload["delta_vs_baseline"]["iran"] == 2
    assert payload["delta_vs_baseline"]["russia"] == 1
    # No prior snapshot → every row is new → recent_additions has every
    # region-relevant row (5 of 5 in this fixture; the DPRK row doesn't
    # match any of the 3 buckets).
    assert len(payload["recent_additions"]) == 4
    add_ids = {a["sdn_id"] for a in payload["recent_additions"]}
    assert add_ids == {"1001", "1002", "1003", "1004"}


def test_compute_delta_with_prior_snapshot_extracts_additions(monkeypatch, tmp_path):
    """Second fetch — prior snapshot exists, so diff catches the new
    SDN entries and buckets them by region."""
    from providers import ofac

    monkeypatch.setattr(ofac, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(ofac, "SDN_PATH", tmp_path / "sdn.csv")
    monkeypatch.setattr(ofac, "SDN_PREV_PATH", tmp_path / "sdn-prev.csv")

    # Seed the "current" snapshot path so the rotation moves it to "prev".
    (tmp_path / "sdn.csv").write_text(_FAKE_SDN_PREV, encoding="utf-8")

    def _fake_get(url: str, *, timeout: float = 30.0) -> bytes:
        return _FAKE_SDN_CUR.encode("utf-8")

    monkeypatch.setattr(ofac, "_http_get", _fake_get)

    payload = ofac.compute_delta()
    assert payload["totals"]["iran"] == 2
    # Additions should include the IRGC + GAZPROM entries.
    add_ids = {a["sdn_id"] for a in payload["recent_additions"]}
    assert "1003" in add_ids  # GAZPROM
    assert "1004" in add_ids  # IRGC
    # Iran delta = 2 (cur) - 1 (prev had only NIOC) = 1
    assert payload["delta_vs_baseline"]["iran"] == 1
    # Russia delta = 1 (cur) - 0 (prev) = 1
    assert payload["delta_vs_baseline"]["russia"] == 1
    # No burst (delta < 10 across the board)
    assert payload["burst_alerts"] == []


def test_burst_alerts_fire_when_delta_exceeds_10(monkeypatch, tmp_path):
    """Synthesize 12 new Iran entries between snapshots — burst flag
    should fire."""
    from providers import ofac

    monkeypatch.setattr(ofac, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(ofac, "SDN_PATH", tmp_path / "sdn.csv")
    monkeypatch.setattr(ofac, "SDN_PREV_PATH", tmp_path / "sdn-prev.csv")

    # Empty prior snapshot (file present but no rows).
    (tmp_path / "sdn.csv").write_text("", encoding="utf-8")

    new_rows = "\n".join(
        f"{2000 + i},\"IRAN ENTITY {i}\",\"Entity\",\"[IRAN]\","
        for i in range(12)
    ) + "\n"

    def _fake_get(url: str, *, timeout: float = 30.0) -> bytes:
        return new_rows.encode("utf-8")

    monkeypatch.setattr(ofac, "_http_get", _fake_get)

    payload = ofac.compute_delta()
    assert payload["totals"]["iran"] == 12
    assert payload["delta_vs_baseline"]["iran"] == 12
    assert "iran" in payload["burst_alerts"]


def test_http_get_rejects_non_treasury_host(monkeypatch):
    """The HTTP helper hardcodes the treasury.gov host so a redirect or
    misconfigured URL doesn't pull from arbitrary servers."""
    from providers import ofac

    with pytest.raises(ValueError, match="treasury"):
        ofac._http_get("https://evil.example.com/sdn.csv")


def test_http_get_rejects_non_http_scheme():
    from providers import ofac

    with pytest.raises(ValueError, match="non-http"):
        ofac._http_get("file:///etc/passwd")
