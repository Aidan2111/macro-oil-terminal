"""Integration tests for data-quality wiring (issue #66).

Verifies that each provider service's wrapper correctly calls
record_fetch_success so that /api/data-quality returns non-null
fields for every provider.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.services import data_quality as dq


# ---------------------------------------------------------------------------
# Helper: seed a provider module's _DQ_LAST_FETCH directly to simulate
# a wrapper having been called.
# ---------------------------------------------------------------------------


def _stub_module(name: str, state: dict) -> tuple[str, object]:
    """Inject a fake ``backend.services.<name>`` with ``get_last_fetch_state``.

    Returns ``(full_name, original_module_or_None)`` so callers can restore.
    """
    full = f"backend.services.{name}"
    original = sys.modules.get(full)
    mod = types.ModuleType(full)
    mod.get_last_fetch_state = lambda s=state: dict(s)  # type: ignore[attr-defined]
    sys.modules[full] = mod
    return full, original


def _restore_modules(saved: list[tuple[str, object]]) -> None:
    """Restore sys.modules to the original entries captured by _stub_module."""
    for full, original in saved:
        if original is None:
            sys.modules.pop(full, None)
        else:
            sys.modules[full] = original


# ---------------------------------------------------------------------------
# 1. Round-trip: all providers report non-null after a successful fetch
# ---------------------------------------------------------------------------


def test_all_providers_non_null_after_success():
    """After a successful fetch, every provider should report non-null
    last_good_at and n_obs in the data-quality envelope."""
    now = datetime.now(timezone.utc)
    state = {
        "last_good_at": now - timedelta(seconds=30),
        "n_obs": 42,
        "latency_ms": 150,
        "message": None,
        "status": "green",
    }
    saved: list[tuple[str, object]] = []
    try:
        for mod_name in (
            "spread_service",
            "inventory_service",
            "cftc_service",
            "fleet_service",
            "alpaca_service",
            "thesis_service",
        ):
            saved.append(_stub_module(mod_name, state))

        env = dq.compute_quality_envelope()

        assert env.overall == "green"
        for provider in env.providers:
            assert provider.last_good_at is not None, (
                f"{provider.name}: last_good_at is null"
            )
            assert provider.n_obs is not None, (
                f"{provider.name}: n_obs is null"
            )
            assert provider.n_obs == 42
    finally:
        _restore_modules(saved)


# ---------------------------------------------------------------------------
# 2. Verify each service's wrapper calls record_fetch_success
# ---------------------------------------------------------------------------


def test_inventory_service_wiring():
    """inventory_service.get_inventory_response wrapper calls record_fetch_success."""
    from backend.services import inventory_service

    fake_resp = MagicMock()
    fake_resp.history = [MagicMock() for _ in range(10)]
    # Provide .date and .commercial_bbls for the guard path
    for i, p in enumerate(fake_resp.history):
        p.date = f"2026-04-{10+i:02d}"
        p.commercial_bbls = 400_000_000

    with patch.object(
        inventory_service, "_real_get_inventory_response", return_value=fake_resp
    ):
        inventory_service.get_inventory_response()

    state = inventory_service.get_last_fetch_state()
    assert state["last_good_at"] is not None
    assert state["n_obs"] == 10
    assert isinstance(state["latency_ms"], int)
    assert state["status"] == "green"


def test_cftc_service_wiring():
    """cftc_service.get_cftc_response wrapper calls record_fetch_success."""
    from backend.services import cftc_service

    fake_resp = MagicMock()
    fake_resp.history = [MagicMock() for _ in range(156)]
    for p in fake_resp.history:
        p.date = "2026-04-22"
        p.mm_net = 150000

    with patch.object(
        cftc_service, "_real_get_cftc_response", return_value=fake_resp
    ):
        cftc_service.get_cftc_response()

    state = cftc_service.get_last_fetch_state()
    assert state["last_good_at"] is not None
    assert state["n_obs"] == 156
    assert isinstance(state["latency_ms"], int)
    assert state["status"] == "green"


@pytest.mark.asyncio
async def test_fleet_service_wiring():
    """fleet_service.publish_delta wrapper calls record_fetch_success."""
    from backend.services import fleet_service

    vessel = {
        "Vessel_Name": "TEST TANKER",
        "MMSI": 366000001,
        "Cargo_Volume_bbls": 1_400_000,
        "Destination": "Houston",
        "Flag_State": "United States",
        "Latitude": 29.0,
        "Longitude": -90.0,
    }
    await fleet_service.publish_delta(vessel)

    state = fleet_service.get_last_fetch_state()
    assert state["last_good_at"] is not None
    assert state["n_obs"] is not None
    assert isinstance(state["n_obs"], int)
    assert state["n_obs"] >= 1
    assert isinstance(state["latency_ms"], int)
    assert state["status"] == "green"


def test_alpaca_service_wiring():
    """alpaca_service.fetch_account wrapper calls record_fetch_success."""
    from backend.services import alpaca_service

    fake_acct = MagicMock()
    fake_acct.status = "ACTIVE"
    fake_acct.buying_power = "100000.00"
    fake_acct.cash = "50000.00"
    fake_acct.equity = "100000.00"
    fake_acct.portfolio_value = "100000.00"

    fake_client = MagicMock()
    fake_client.get_account.return_value = fake_acct

    with patch.object(alpaca_service, "get_client", return_value=fake_client):
        result = alpaca_service.fetch_account()

    state = alpaca_service.get_last_fetch_state()
    assert state["last_good_at"] is not None
    assert state["n_obs"] == 1
    assert isinstance(state["latency_ms"], int)
    assert state["status"] == "green"
    assert result["equity"] == 100000.0


def test_thesis_service_wiring():
    """thesis_service.get_latest_thesis wrapper calls record_fetch_success."""
    from backend.services import thesis_service

    fake_record = {"timestamp": "2026-04-27T12:00:00Z", "thesis": {"stance": "long"}}

    with patch.object(
        thesis_service, "_real_get_latest_thesis", return_value=fake_record
    ):
        result = thesis_service.get_latest_thesis()

    state = thesis_service.get_last_fetch_state()
    assert state["last_good_at"] is not None
    assert state["n_obs"] == 1
    assert isinstance(state["latency_ms"], int)
    assert state["status"] == "green"
    assert result == fake_record


# ---------------------------------------------------------------------------
# 3. Failure path: record_fetch_failure sets status=red
# ---------------------------------------------------------------------------


def test_inventory_service_failure_records_red():
    """When the upstream provider raises, record_fetch_failure should fire."""
    from backend.services import inventory_service

    with patch.object(
        inventory_service,
        "_real_get_inventory_response",
        side_effect=RuntimeError("EIA down"),
    ):
        with pytest.raises(RuntimeError, match="EIA down"):
            inventory_service.get_inventory_response()

    state = inventory_service.get_last_fetch_state()
    assert state["status"] == "red"
    assert "EIA down" in str(state["message"])


def test_alpaca_service_failure_records_red():
    """When Alpaca is unreachable, record_fetch_failure should fire."""
    from backend.services import alpaca_service

    with patch.object(
        alpaca_service, "get_client", side_effect=RuntimeError("Alpaca unreachable"),
    ):
        with pytest.raises(RuntimeError, match="Alpaca unreachable"):
            alpaca_service.fetch_account()

    state = alpaca_service.get_last_fetch_state()
    assert state["status"] == "red"
    assert "Alpaca unreachable" in str(state["message"])
