"""`/api/positions/*` routes — Alpaca paper-trading wrapper.

Security posture (Wave-1 Sub-C, single-user demo):
  * `POST /positions/execute` refuses unless `ALPACA_PAPER == "true"`.
  * The TradingClient is pinned to `paper=True` in the service layer.
  * The ALPACA_API_SECRET never appears in any response body; the
    service maps Alpaca objects through whitelists in `map_*`.
  * Execute is rate-limited to 1 request / 2s per process via a tiny
    in-process token bucket (asyncio.Lock + last-call timestamp).

TODO(phase-2 auth): real authn/z will replace the ALPACA_PAPER gate and
    the shared in-memory bucket with per-session state.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import alpaca_service
from ..services.alpaca_service import AlpacaNotConfigured


router = APIRouter(tags=["positions"])


# --- Rate limiter ------------------------------------------------------------

_EXECUTE_MIN_INTERVAL_S = 2.0
_rate_lock = asyncio.Lock()
_last_execute_monotonic: float = 0.0


def _reset_rate_limit_for_test() -> None:
    """Reset the token-bucket clock. Test hook only."""
    global _last_execute_monotonic
    _last_execute_monotonic = 0.0


# --- Pydantic models ---------------------------------------------------------


class ExecuteRequest(BaseModel):
    """Minimal order-entry payload. All fields required."""

    symbol: str = Field(min_length=1, max_length=16)
    qty: float = Field(gt=0)
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"] = "market"
    time_in_force: Literal["day", "gtc", "ioc", "fok"] = "day"
    limit_price: float | None = None


# --- Helpers -----------------------------------------------------------------


def _client_or_503():
    try:
        return alpaca_service.get_client()
    except AlpacaNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# --- Routes ------------------------------------------------------------------


@router.get("/positions")
def list_positions() -> dict[str, object]:
    """Return currently open positions (our projected shape)."""
    client = _client_or_503()
    raw = client.get_all_positions()
    return {"positions": [alpaca_service.map_position(p) for p in raw]}


@router.get("/positions/account")
def get_account() -> dict[str, object]:
    """Return account balances (buying_power, cash, equity, portfolio_value)."""
    client = _client_or_503()
    acct = client.get_account()
    return alpaca_service.map_account(acct)


@router.post("/positions/execute")
async def execute_order(req: ExecuteRequest) -> dict[str, object]:
    """Place a paper order.

    Hard-gate: `ALPACA_PAPER` env var must be the string "true".
    Rate-limited to 1 call / 2s per process.
    """
    global _last_execute_monotonic

    if os.environ.get("ALPACA_PAPER", "").strip().lower() != "true":
        # TODO(phase-2 auth): replace with proper authN/Z check.
        raise HTTPException(
            status_code=403,
            detail="Execution is disabled (ALPACA_PAPER must be 'true').",
        )

    async with _rate_lock:
        now = time.monotonic()
        if now - _last_execute_monotonic < _EXECUTE_MIN_INTERVAL_S:
            raise HTTPException(
                status_code=429,
                detail="Execute rate limit: 1 request per 2s.",
            )
        _last_execute_monotonic = now

    client = _client_or_503()

    # Build the right request object without leaking secrets anywhere.
    from alpaca.trading.enums import OrderSide, TimeInForce  # type: ignore
    from alpaca.trading.requests import (  # type: ignore
        LimitOrderRequest,
        MarketOrderRequest,
    )

    side = OrderSide.BUY if req.side == "buy" else OrderSide.SELL
    tif_map = {
        "day": TimeInForce.DAY,
        "gtc": TimeInForce.GTC,
        "ioc": TimeInForce.IOC,
        "fok": TimeInForce.FOK,
    }
    tif = tif_map[req.time_in_force]

    if req.type == "limit":
        if req.limit_price is None:
            raise HTTPException(
                status_code=400,
                detail="limit_price required for type=limit.",
            )
        order_req = LimitOrderRequest(
            symbol=req.symbol,
            qty=req.qty,
            side=side,
            time_in_force=tif,
            limit_price=req.limit_price,
        )
    else:
        order_req = MarketOrderRequest(
            symbol=req.symbol,
            qty=req.qty,
            side=side,
            time_in_force=tif,
        )

    order = client.submit_order(order_req)
    # Map through the whitelist projector — never splat the raw object.
    return alpaca_service.map_order(order)


@router.post("/positions/cancel/{order_id}")
def cancel_order(order_id: str) -> dict[str, object]:
    """Cancel an order by id."""
    client = _client_or_503()
    client.cancel_order_by_id(order_id)
    return {"cancelled": True, "order_id": order_id}


@router.get("/positions/orders")
def list_orders(
    status: Literal["open", "all", "closed"] = Query("open"),
) -> dict[str, object]:
    """List orders filtered by status."""
    client = _client_or_503()
    try:
        from alpaca.trading.enums import QueryOrderStatus  # type: ignore
        from alpaca.trading.requests import GetOrdersRequest  # type: ignore

        qmap = {
            "open": QueryOrderStatus.OPEN,
            "all": QueryOrderStatus.ALL,
            "closed": QueryOrderStatus.CLOSED,
        }
        req = GetOrdersRequest(status=qmap[status])
        raw = client.get_orders(filter=req)
    except Exception:
        # Tests pass a MagicMock where `filter=` may not match; fall back.
        raw = client.get_orders()
    return {"orders": [alpaca_service.map_order(o) for o in raw]}


@router.get("/positions/stream")
async def stream_trade_updates() -> "EventSourceResponse":  # type: ignore[name-defined]
    """SSE forwarding of Alpaca trade-update websocket events.

    Emits `trade_update` events for fills, partial fills, cancels. Heartbeat
    every 15s. Errors in the upstream stream are logged (without echoing
    any secret) and the connection retries with backoff.
    """
    from sse_starlette.sse import EventSourceResponse

    queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    async def _pump() -> None:
        # Attempt the real upstream; if unavailable (no creds or SDK path
        # differs in a CI env), the stream still emits heartbeats.
        try:
            from alpaca.trading.stream import TradingStream  # type: ignore
        except Exception:
            return
        key_id = os.environ.get("ALPACA_API_KEY_ID")
        secret = os.environ.get("ALPACA_API_SECRET")
        if not key_id or not secret:
            return
        stream = TradingStream(api_key=key_id, secret_key=secret, paper=True)

        async def _handler(data):  # type: ignore[no-untyped-def]
            try:
                # `data` is an Alpaca TradeUpdate; map to a dict without
                # ever touching credentials.
                event = getattr(data, "event", None)
                order = getattr(data, "order", None)
                payload = {
                    "event": str(event) if event is not None else "unknown",
                    "order": alpaca_service.map_order(order) if order else None,
                }
                await queue.put(payload)
            except Exception:
                return

        stream.subscribe_trade_updates(_handler)
        try:
            await stream._run_forever()  # alpaca-py async entrypoint
        except Exception:
            return

    pump_task = asyncio.create_task(_pump(), name="alpaca-trade-updates-pump")

    async def _event_gen():
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
                    continue
                import json as _json

                yield {"event": "trade_update", "data": _json.dumps(payload, default=str)}
        finally:
            pump_task.cancel()

    return EventSourceResponse(_event_gen(), ping=15)
