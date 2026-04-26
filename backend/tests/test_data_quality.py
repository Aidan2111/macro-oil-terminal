"""Smoke tests for backend/services/data_quality.py.

We don't talk to upstream providers in unit tests — we monkeypatch
``__import__`` indirectly by stuffing a fake state into each provider
module before invoking ``compute_quality_envelope``.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import data_quality as dq


def _stub_module(name: str, state: dict) -> None:
    """Inject a fake ``backend.services.<name>`` with ``get_last_fetch_state``."""
    full = f"backend.services.{name}"
    mod = types.ModuleType(full)
    mod.get_last_fetch_state = lambda s=state: dict(s)  # type: ignore[attr-defined]
    sys.modules[full] = mod


def test_envelope_all_green(monkeypatch):
    now = datetime.now(timezone.utc)
    fresh = {
        "last_good_at": now - timedelta(minutes=2),
        "n_obs": 251,
        "latency_ms": 180,
        "message": None,
        "status": "green",
    }
    for sub in (
        "spread_service",
        "inventory_service",
        "cftc_service",
        "fleet_service",
        "alpaca_service",
        "thesis_service",
    ):
        _stub_module(sub, fresh)

    env = dq.compute_quality_envelope()
    assert env.overall == "green"
    assert {p.name for p in env.providers} == {
        "yfinance", "eia", "cftc", "aisstream", "alpaca_paper", "audit_log",
    }
    yf = next(p for p in env.providers if p.name == "yfinance")
    assert yf.status == "green"
    assert yf.n_obs == 251


def test_envelope_amber_on_stale(monkeypatch):
    now = datetime.now(timezone.utc)
    stale = {
        # Older than the 6-h SLA but fresher than 12 h — should age to amber.
        "last_good_at": now - timedelta(hours=8),
        "n_obs": 10,
        "latency_ms": 200,
        "message": None,
        "status": "green",
    }
    fresh = {
        "last_good_at": now,
        "n_obs": 1,
        "latency_ms": 10,
        "message": None,
        "status": "green",
    }
    _stub_module("spread_service", stale)
    _stub_module("inventory_service", fresh)
    _stub_module("cftc_service", fresh)
    _stub_module("fleet_service", fresh)
    _stub_module("alpaca_service", fresh)
    _stub_module("thesis_service", fresh)

    env = dq.compute_quality_envelope()
    assert env.overall == "amber"
    yf = next(p for p in env.providers if p.name == "yfinance")
    assert yf.status == "amber"


def test_envelope_red_on_explicit_failure(monkeypatch):
    now = datetime.now(timezone.utc)
    bad = {
        "last_good_at": None,
        "n_obs": None,
        "latency_ms": None,
        "message": "yfinance rate-limited",
        "status": "red",
    }
    fresh = {
        "last_good_at": now,
        "n_obs": 1,
        "latency_ms": 10,
        "message": None,
        "status": "green",
    }
    _stub_module("spread_service", bad)
    for sub in ("inventory_service", "cftc_service", "fleet_service",
                "alpaca_service", "thesis_service"):
        _stub_module(sub, fresh)

    env = dq.compute_quality_envelope()
    assert env.overall == "red"
    yf = next(p for p in env.providers if p.name == "yfinance")
    assert yf.status == "red"
    assert yf.message == "yfinance rate-limited"


def test_guard_yfinance_empty_frame_raises():
    with pytest.raises(dq.GuardViolation):
        dq.guard_yfinance_frame(None)


def test_guard_eia_negative_inventory_raises():
    with pytest.raises(dq.GuardViolation):
        dq.guard_eia_inventory([{"date": "2026-04-20", "commercial_bbls": -1}])


def test_guard_cftc_out_of_range():
    with pytest.raises(dq.GuardViolation):
        dq.guard_cftc([{"date": "2026-04-22", "value": 9_999_999}])


def test_guard_aisstream_zero_mmsi():
    with pytest.raises(dq.GuardViolation):
        dq.guard_aisstream_vessels([{"mmsi": 0, "lat": 0.0, "lon": 0.0}])


def test_guard_alpaca_inactive_status():
    with pytest.raises(dq.GuardViolation):
        dq.guard_alpaca_account({"status": "REJECTED", "buying_power": 1.0})
