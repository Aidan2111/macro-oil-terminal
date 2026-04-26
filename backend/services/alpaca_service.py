"""Thin wrapper around alpaca-py's TradingClient.

Secret discipline
-----------------
The `ALPACA_API_SECRET` env var is read once, handed to the TradingClient
constructor, and NEVER re-emitted. Nothing in this module (or any caller)
logs or echoes it; the service boundary is the only place the secret
lives.

`paper=True` is hard-coded. This is non-negotiable until an auth layer
ships. See the security section of the Wave-1 Sub-C brief.

TODO(phase-2 auth): add per-user credential binding + a server-side
authenticator so `paper=False` execution can be safely gated.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from . import _compat  # noqa: F401


class AlpacaNotConfigured(RuntimeError):
    """Raised when `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET` are unset."""


_client: Any = None
_client_lock = threading.Lock()


def get_client() -> Any:
    """Return a cached TradingClient bound to paper trading.

    Raises
    ------
    AlpacaNotConfigured
        If either required env var is missing/empty.
    """
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        key_id = os.environ.get("ALPACA_API_KEY_ID")
        secret = os.environ.get("ALPACA_API_SECRET")
        if not key_id or not secret:
            raise AlpacaNotConfigured(
                "ALPACA_API_KEY_ID and ALPACA_API_SECRET must both be set."
            )
        from alpaca.trading.client import TradingClient  # type: ignore

        # paper=True is hard-coded by policy; do not parameterise it.
        _client = TradingClient(api_key=key_id, secret_key=secret, paper=True)
        return _client


# --- Projections -------------------------------------------------------------


def _as_float(value: Any, default: float = 0.0) -> float:
    """Alpaca often returns stringy numerics; coerce defensively."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def map_position(p: Any) -> dict[str, Any]:
    """Alpaca Position -> our frontend shape."""
    return {
        "symbol": getattr(p, "symbol", None),
        "qty": _as_float(getattr(p, "qty", 0)),
        "avg_entry": _as_float(getattr(p, "avg_entry_price", 0)),
        "current_px": _as_float(getattr(p, "current_price", 0)),
        "unrealized_pnl": _as_float(getattr(p, "unrealized_pl", 0)),
        "unrealized_pnl_pct": _as_float(getattr(p, "unrealized_plpc", 0)),
    }


def map_account(a: Any) -> dict[str, Any]:
    """Alpaca TradeAccount -> our frontend shape."""
    return {
        "buying_power": _as_float(getattr(a, "buying_power", 0)),
        "cash": _as_float(getattr(a, "cash", 0)),
        "equity": _as_float(getattr(a, "equity", 0)),
        "portfolio_value": _as_float(getattr(a, "portfolio_value", 0)),
    }


def map_order(o: Any) -> dict[str, Any]:
    """Alpaca Order -> a small dict that never leaks credentials."""
    return {
        "id": str(getattr(o, "id", "")),
        "status": str(getattr(o, "status", "")),
        "symbol": getattr(o, "symbol", None),
        "qty": _as_float(getattr(o, "qty", 0)),
        "side": str(getattr(o, "side", "")),
    }
