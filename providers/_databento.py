"""Databento pricing provider (primary, key-gated).

Databento Stocks Starter (~$29/mo) + Futures dataset provides real-time
CL (CME WTI) and BZ (ICE Brent) tick data. This module implements the
primary pricing source when ``DATABENTO_API_KEY`` is set; yfinance is
the fallback.

Supported intervals: daily, intraday (1min, 5min, 15min, 1h).

Symbols:
  - ``CL.FUT`` — CME front-month WTI crude oil
  - ``BZ.FUT`` — ICE front-month Brent crude oil

Key env var: ``DATABENTO_API_KEY``
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd


def _api_key() -> Optional[str]:
    """Return Databento API key if configured, else None."""
    return os.environ.get("DATABENTO_API_KEY")


def _ensure_sdk() -> None:
    """Raise if databento SDK is not installed."""
    try:
        import databento
    except ImportError:
        raise RuntimeError(
            "databento SDK not installed. Run: pip install databento"
        )


def _fetch_symbol(
    symbol: str,
    interval: str = "1D",
    start: Optional[str] = None,
    end: Optional[str] = None,
    outputsize: Optional[int] = None,
) -> pd.Series:
    """Pull one Databento symbol and return a Close series.

    Uses the Databento Python SDK's ``Timeseries.get_range()`` endpoint.

    Parameters
    ----------
    symbol : str
        Databento symbol, e.g. "CL.FUT" or "BZ.FUT"
    interval : str
        Time bar interval: "1D", "1H", "15m", "5m", "1min"
    start : str, optional
        Start date in YYYY-MM-DD format. Defaults to 5 years ago.
    end : str, optional
        End date in YYYY-MM-DD format. Defaults to today.
    outputsize : int, optional
        Maximum number of rows to return. If None, returns all.
    """
    key = _api_key()
    if not key:
        raise RuntimeError("DATABENTO_API_KEY not set")

    _ensure_sdk()
    import databento as db

    # Map interval to Databento schema
    schema = _interval_to_schema(interval)

    # Defaults
    if end is None:
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if start is None:
        start_dt = datetime.now(timezone.utc) - timedelta(days=5 * 365)
        start = start_dt.strftime("%Y-%m-%d")

    client = db.Historical(key)

    # Use timeseries.get_range for historical OHLCV bars
    params = dict(
        dataset="GLBX.MDP3",  # CME MDP3 market data
        symbols=[symbol],
        schema=schema,
        start=start,
        end=end,
    )

    if outputsize is not None:
        params["limit"] = outputsize

    data = client.timeseries.get_range(**params)

    if not data:
        raise RuntimeError(f"databento returned zero rows for {symbol}")

    # Parse response into DataFrame
    df = pd.DataFrame(data)

    if df.empty:
        raise RuntimeError(f"databento returned empty dataframe for {symbol}")

    # Extract close prices
    if "close_px" in df.columns:
        closes = df.set_index("ts_event")["close_px"]
    elif "close" in df.columns:
        closes = df.set_index("ts_event")["close"]
    else:
        raise RuntimeError(
            f"databento response missing close price column for {symbol}. "
            f"Columns: {list(df.columns)}"
        )

    closes.index = pd.to_datetime(closes.index, utc=True)
    closes = closes.sort_index()
    closes.name = symbol
    return closes


def _interval_to_schema(interval: str) -> str:
    """Map interval string to Databento schema.

    Databento supports:
      - ohlcv-1d (daily)
      - ohlcv-1h (hourly)
      - ohlcv-1m (1-minute)
    """
    interval_lower = interval.lower().strip()
    if interval_lower in ("1d", "1day", "daily"):
        return "ohlcv-1d"
    elif interval_lower in ("1h", "1hour", "hourly"):
        return "ohlcv-1h"
    elif interval_lower in ("1min", "1m", "1minute"):
        return "ohlcv-1m"
    elif interval_lower in ("5m", "5min", "5minute"):
        return "ohlcv-1m"  # Will need resampling
    elif interval_lower in ("15m", "15min", "15minute"):
        return "ohlcv-1m"  # Will need resampling
    else:
        raise ValueError(
            f"Unsupported interval: {interval}. "
            "Use 1D/1H/1min for Databento futures data."
        )


def fetch_daily(years: int = 5) -> pd.DataFrame:
    """Return daily Brent/WTI via Databento. Columns Brent, WTI; DatetimeIndex."""
    n_days = max(32, int(years * 365))
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_dt = datetime.now(timezone.utc) - timedelta(days=n_days)
    start = start_dt.strftime("%Y-%m-%d")

    brent = _fetch_symbol("BZ.FUT", interval="1D", start=start, end=end)
    wti = _fetch_symbol("CL.FUT", interval="1D", start=start, end=end)

    df = pd.concat({"Brent": brent, "WTI": wti}, axis=1).dropna()
    if df.empty:
        raise RuntimeError("databento: no overlapping Brent/WTI bars")

    df.index.name = "Date"
    # Ensure clean forward-fill for weekends/holidays
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full_idx).ffill().bfill()
    return df


def fetch_intraday(interval: str = "1min", period: str = "2d") -> pd.DataFrame:
    """Return intraday Brent/WTI bars.

    interval in {1min, 5min, 15min, 1h}
    period controls lookback (e.g. "2d" = last 2 days)
    """
    # Calculate start/end from period
    now = datetime.now(timezone.utc)
    end = now.strftime("%Y-%m-%d")

    if period.endswith("d"):
        days = int(period[:-1])
    elif period.endswith("h"):
        days = max(1, int(period[:-1]) // 24)
    else:
        days = 2

    start_dt = now - timedelta(days=days)
    start = start_dt.strftime("%Y-%m-%d")

    brent = _fetch_symbol("BZ.FUT", interval=interval, start=start, end=end)
    wti = _fetch_symbol("CL.FUT", interval=interval, start=start, end=end)

    df = pd.concat({"Brent": brent, "WTI": wti}, axis=1).dropna(how="any")
    if df.empty:
        raise RuntimeError("databento: no overlapping intraday bars")

    df.index.name = "Datetime"
    return df


def health_check(timeout: float = 6.0) -> dict:
    """Return a health-check dict: ok / latency_ms / note."""
    key = _api_key()
    if not key:
        return {"ok": False, "latency_ms": 0, "note": "no DATABENTO_API_KEY set"}

    import time
    t0 = time.monotonic()
    try:
        _ensure_sdk()
        import databento as db

        client = db.Historical(key)
        # Quick probe: request 1 day of OHLCV data for CL.FUT
        data = client.timeseries.get_range(
            dataset="GLBX.MDP3",
            symbols=["CL.FUT"],
            schema="ohlcv-1d",
            start=(datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d"),
            end=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        ok = data is not None and len(data) > 0
        return {
            "ok": bool(ok),
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": "" if ok else "empty response",
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": repr(exc)[:120],
        }


__all__ = ["fetch_daily", "fetch_intraday", "health_check"]