"""Unit tests for the provider orchestrators."""

from __future__ import annotations


def test_active_pricing_provider_default(monkeypatch):
    from providers.pricing import active_pricing_provider
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    label = active_pricing_provider("intraday")
    assert "Yahoo Finance" in label


def test_active_pricing_provider_with_twelvedata(monkeypatch):
    from providers.pricing import active_pricing_provider
    monkeypatch.setenv("TWELVEDATA_API_KEY", "stub")
    label = active_pricing_provider("daily")
    assert "Twelve Data" in label


def test_active_inventory_provider(monkeypatch):
    from providers.inventory import active_inventory_provider
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert "EIA" in active_inventory_provider()
    monkeypatch.setenv("FRED_API_KEY", "stub")
    assert "FRED" in active_inventory_provider()


def test_active_ais_provider(monkeypatch):
    from providers.ais import active_ais_provider
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    assert "Historical" in active_ais_provider()
    monkeypatch.setenv("AISSTREAM_API_KEY", "stub")
    assert "aisstream.io" in active_ais_provider()
