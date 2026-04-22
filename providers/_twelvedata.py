"""Twelve Data pricing provider (secondary, key-gated).

Free tier: 800 calls/day, 8/min. Symbols: ``BRN/USD`` (Brent) and
``WTI/USD``. Keyed on ``TWELVE_DATA_API_KEY`` / ``TWELVEDATA_API_KEY``
(we accept either). Returns the same columns as yfinance for drop-in
substitution.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests


_BASE = "https://api.twelvedata.com/time_series"


def _api_key() -> Optional[str]:
    return os.environ.get("TWELVE_DATA_API_KEY") or os.environ.get("TWELVEDATA_API_KEY")


def _fetch_symbol(symbol: str, interval: str, outputsize: int) -> pd.Series:
    """Pull one Twelve Data symbol and return a Close series."""
    key = _api_key()
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY not set")
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "format": "JSON",
        "apikey": key,
    }
    resp = requests.get(_BASE, params=params, timeout=12)
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") == "error" or "values" not in body:
        msg = body.get("message", "unknown twelvedata error")
        raise RuntimeError(f"twelvedata error for {symbol}: {msg}")
    rows = body["values"]
    if not rows:
        raise RuntimeError(f"twelvedata returned zero rows for {symbol}")
    idx = pd.DatetimeIndex([pd.Timestamp(r["datetime"]) for r in rows]).sort_values()
    closes = pd.Series(
        [float(r["close"]) for r in rows],
        index=[pd.Timestamp(r["datetime"]) for r in rows],
        name=symbol,
    ).sort_index()
    return closes


def fetch_daily(years: int = 5) -> pd.DataFrame:
    """Return daily Brent/WTI via Twelve Data. Columns Brent, WTI; DatetimeIndex."""
    n_days = max(32, int(years * 365))
    brent = _fetch_symbol("BRN/USD", interval="1day", outputsize=min(n_days, 5000))
    wti = _fetch_symbol("WTI/USD", interval="1day", outputsize=min(n_days, 5000))
    df = pd.concat({"Brent": brent, "WTI": wti}, axis=1).dropna()
    if df.empty:
        raise RuntimeError("twelvedata: no overlapping Brent/WTI bars")
    df.index.name = "Date"
    return df


def fetch_intraday(interval: str = "1min", outputsize: int = 500) -> pd.DataFrame:
    """Return intraday Brent/WTI bars. interval in {1min, 5min, 15min, 30min, 1h}."""
    brent = _fetch_symbol("BRN/USD", interval=interval, outputsize=outputsize)
    wti = _fetch_symbol("WTI/USD", interval=interval, outputsize=outputsize)
    df = pd.concat({"Brent": brent, "WTI": wti}, axis=1).dropna(how="any")
    if df.empty:
        raise RuntimeError("twelvedata: no overlapping intraday bars")
    df.index.name = "Datetime"
    return df


def health_check(timeout: float = 6.0) -> dict:
    """Return a health-check dict: ok / latency_ms / note."""
    key = _api_key()
    if not key:
        return {"ok": False, "latency_ms": 0, "note": "no api key set"}
    import time
    t0 = time.monotonic()
    try:
        resp = requests.get(
            _BASE,
            params={"symbol": "BRN/USD", "interval": "1day", "outputsize": 1, "apikey": key},
            timeout=timeout,
        )
        ok = resp.status_code == 200 and "values" in (resp.json() or {})
        return {
            "ok": bool(ok),
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": "" if ok else f"status={resp.status_code}",
        }
    except Exception as exc:
        return {"ok": False, "latency_ms": int((time.monotonic() - t0) * 1000), "note": repr(exc)[:120]}


__all__ = ["fetch_daily", "fetch_intraday", "health_check"]
