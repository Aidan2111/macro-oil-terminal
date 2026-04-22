"""Unit tests for the data-ingestion layer (real EIA via fixture)."""

from __future__ import annotations

import os

import pandas as pd
import pytest


def test_inventory_via_fixture(eia_fixture):
    import data_ingestion as di
    res = di.fetch_inventory_data()
    assert res.frame is not None and not res.frame.empty
    for col in ("Commercial_bbls", "SPR_bbls", "Total_Inventory_bbls"):
        assert col in res.frame.columns
    last = float(res.frame["Commercial_bbls"].iloc[-1])
    # Real current-era range for US commercial crude ex-SPR
    assert 300e6 < last < 700e6


def test_inventory_source_and_timestamp(eia_fixture):
    import data_ingestion as di
    res = di.fetch_inventory_data()
    assert res.source == "EIA"
    assert res.source_url.startswith("https://www.eia.gov/")
    assert isinstance(res.fetched_at, pd.Timestamp)


def test_ais_placeholder_has_notice_without_key():
    import data_ingestion as di
    # Env is scrubbed by the autouse fixture — no AISSTREAM_API_KEY present.
    res = di.fetch_ais_data(n_vessels=200)
    assert not res.is_live
    assert res.snapshot_notice is not None
    assert "aisstream.io" in res.snapshot_notice
    assert len(res.frame) == 200
    for col in ("Vessel_Name", "MMSI", "Cargo_Volume_bbls",
                "Destination", "Flag_State", "Latitude", "Longitude"):
        assert col in res.frame.columns


def test_simulators_not_on_public_api():
    import data_ingestion as di
    assert not hasattr(di, "simulate_inventory")
    assert not hasattr(di, "generate_ais_mock")


def test_cushing_series_present(eia_fixture):
    import data_ingestion as di
    res = di.fetch_inventory_data()
    assert "Cushing_bbls" in res.frame.columns
    last = float(res.frame["Cushing_bbls"].dropna().iloc[-1])
    # Cushing sits in roughly 15–60M bbl range through the 2020s
    assert 10e6 < last < 100e6


def test_inventory_unavailable_raises(monkeypatch):
    """If both EIA and FRED fail, InventoryUnavailable propagates."""
    import providers.inventory as inv

    def _fail(): raise RuntimeError("upstream down")
    monkeypatch.setattr(inv, "_try_eia", lambda: _fail())
    monkeypatch.setattr(inv, "_try_fred", lambda: _fail())

    with pytest.raises(inv.InventoryUnavailable):
        inv.fetch_inventory()
