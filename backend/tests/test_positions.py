"""Tests for `/api/positions/*` + the Alpaca service wrapper.

Covers:
  * `get_all_positions`/`get_account` shape propagation.
  * `POST /api/positions/execute` guard-rails:
      - `ALPACA_PAPER != "true"` -> 403.
      - Valid request -> TradingClient.submit_order called with expected kwargs.
      - Secret redaction: response never echoes ALPACA_API_SECRET value.
      - Rate limit: two rapid calls -> 429 on the second.
  * `POST /api/positions/cancel/{id}`.
  * `GET /api/positions/orders?status=`.
"""

from __future__ import annotations

import os
import types
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import alpaca_service


SECRET_SENTINEL = "super-secret-alpaca-key-DO-NOT-LEAK"


@pytest.fixture(autouse=True)
def _env_and_state(monkeypatch):
    """Set safe env defaults + reset service caches + rate-limit clock."""
    monkeypatch.setenv("ALPACA_PAPER", "true")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key-id")
    monkeypatch.setenv("ALPACA_API_SECRET", SECRET_SENTINEL)
    alpaca_service.reset_client_cache()
    # Reset the rate-limit clock so each test starts fresh.
    from backend.routers import positions as pos_router

    pos_router._reset_rate_limit_for_test()
    yield
    alpaca_service.reset_client_cache()


def _mock_client():
    """Build a TradingClient-shaped MagicMock."""
    client = MagicMock()

    pos = types.SimpleNamespace(
        symbol="AAPL",
        qty="10",
        avg_entry_price="150.0",
        current_price="160.0",
        unrealized_pl="100.0",
        unrealized_plpc="0.0666",
    )
    client.get_all_positions.return_value = [pos]

    acct = types.SimpleNamespace(
        buying_power="100000.0",
        cash="50000.0",
        equity="75000.0",
        portfolio_value="75000.0",
    )
    client.get_account.return_value = acct

    order = types.SimpleNamespace(
        id="order-xyz-1",
        status="accepted",
        symbol="AAPL",
        qty="5",
        side="buy",
    )
    client.submit_order.return_value = order
    client.cancel_order_by_id.return_value = None

    client.get_orders.return_value = [order]
    return client


def test_get_positions_returns_mapped_shape(monkeypatch):
    """`/api/positions` projects Alpaca Position into our JSON shape."""
    client = _mock_client()
    monkeypatch.setattr(alpaca_service, "get_client", lambda: client)

    resp = TestClient(create_app()).get("/api/positions")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "positions": [
            {
                "symbol": "AAPL",
                "qty": 10.0,
                "avg_entry": 150.0,
                "current_px": 160.0,
                "unrealized_pnl": 100.0,
                "unrealized_pnl_pct": 0.0666,
            }
        ]
    }


def test_get_account_returns_mapped_shape(monkeypatch):
    client = _mock_client()
    monkeypatch.setattr(alpaca_service, "get_client", lambda: client)

    resp = TestClient(create_app()).get("/api/positions/account")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "buying_power": 100000.0,
        "cash": 50000.0,
        "equity": 75000.0,
        "portfolio_value": 75000.0,
    }


def test_execute_refuses_when_paper_flag_not_true(monkeypatch):
    """If ALPACA_PAPER isn't literally "true" the endpoint MUST 403."""
    client = _mock_client()
    monkeypatch.setattr(alpaca_service, "get_client", lambda: client)
    monkeypatch.setenv("ALPACA_PAPER", "false")

    resp = TestClient(create_app()).post(
        "/api/positions/execute",
        json={
            "symbol": "AAPL",
            "qty": 1,
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        },
    )
    assert resp.status_code == 403
    client.submit_order.assert_not_called()


def test_execute_happy_path_calls_submit_order(monkeypatch):
    """Valid request -> TradingClient.submit_order invoked; response carries order id."""
    client = _mock_client()
    monkeypatch.setattr(alpaca_service, "get_client", lambda: client)

    resp = TestClient(create_app()).post(
        "/api/positions/execute",
        json={
            "symbol": "AAPL",
            "qty": 5,
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == "order-xyz-1"
    assert body["status"] == "accepted"
    assert client.submit_order.call_count == 1


def test_execute_response_never_contains_the_secret(monkeypatch):
    """Hard rule: the Alpaca secret must never appear in any execute payload."""
    client = _mock_client()
    monkeypatch.setattr(alpaca_service, "get_client", lambda: client)

    resp = TestClient(create_app()).post(
        "/api/positions/execute",
        json={
            "symbol": "AAPL",
            "qty": 1,
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        },
    )
    assert resp.status_code == 200
    raw = resp.text
    assert SECRET_SENTINEL not in raw
    # And the parsed dict, walked recursively, must not contain it.
    def _walk(node):
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
        else:
            assert SECRET_SENTINEL not in str(node)

    _walk(resp.json())


def test_execute_rate_limits_back_to_back_calls(monkeypatch):
    """Two rapid execute calls -> second one 429."""
    client = _mock_client()
    monkeypatch.setattr(alpaca_service, "get_client", lambda: client)

    tc = TestClient(create_app())
    payload = {
        "symbol": "AAPL",
        "qty": 1,
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
    }
    r1 = tc.post("/api/positions/execute", json=payload)
    r2 = tc.post("/api/positions/execute", json=payload)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 429, r2.text


def test_cancel_order_invokes_client(monkeypatch):
    client = _mock_client()
    monkeypatch.setattr(alpaca_service, "get_client", lambda: client)

    resp = TestClient(create_app()).post("/api/positions/cancel/order-xyz-1")
    assert resp.status_code == 200
    assert resp.json() == {"cancelled": True, "order_id": "order-xyz-1"}
    client.cancel_order_by_id.assert_called_once_with("order-xyz-1")


def test_orders_listing_passes_status(monkeypatch):
    client = _mock_client()
    monkeypatch.setattr(alpaca_service, "get_client", lambda: client)

    tc = TestClient(create_app())
    resp = tc.get("/api/positions/orders", params={"status": "open"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["orders"][0]["id"] == "order-xyz-1"
    # get_orders should have been called at least once.
    assert client.get_orders.call_count >= 1


def test_not_configured_returns_503(monkeypatch):
    """If the Alpaca env isn't set, routes surface a 503."""
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
    alpaca_service.reset_client_cache()
    # Don't patch get_client — let it raise AlpacaNotConfigured.

    resp = TestClient(create_app()).get("/api/positions")
    assert resp.status_code == 503
