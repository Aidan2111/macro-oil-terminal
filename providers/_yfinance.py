"""yfinance-backed pricing provider — daily (5y) and intraday (1-min)."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None


def fetch_daily(years: int = 5) -> pd.DataFrame:
    """Return 5y daily Brent/WTI (columns Brent, WTI, DatetimeIndex named Date)."""
    if yf is None:
        raise RuntimeError("yfinance not installed")

    end = datetime.utcnow()
    start = end - timedelta(days=years * 365)

    raw = yf.download(
        tickers=["BZ=F", "CL=F"],
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        group_by="column",
        threads=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned empty daily frame")

    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw["Adj Close"]
    else:
        close = raw[["Close"]] if "Close" in raw.columns else raw

    close = close.rename(columns={"BZ=F": "Brent", "CL=F": "WTI"})
    if "Brent" not in close.columns or "WTI" not in close.columns:
        raise RuntimeError("yfinance response missing Brent/WTI columns")

    df = close[["Brent", "WTI"]].copy()
    df.index = pd.to_datetime(df.index)
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full_idx).ffill().bfill()
    df.index.name = "Date"
    if df.isna().all().any() or len(df) < 30:
        raise RuntimeError("yfinance daily frame too short after reindex")
    return df


def fetch_intraday(interval: str = "1m", period: str = "2d") -> pd.DataFrame:
    """Return 1-min Brent/WTI intraday bars.

    yfinance intraday has a ~15min publisher delay for futures — that's
    the practical ceiling without a paid feed. ``period`` can be 1d/2d/5d;
    ``interval`` is typically 1m/5m/15m.
    """
    if yf is None:
        raise RuntimeError("yfinance not installed")

    brent = yf.Ticker("BZ=F").history(period=period, interval=interval, auto_adjust=False)
    wti = yf.Ticker("CL=F").history(period=period, interval=interval, auto_adjust=False)

    if brent is None or brent.empty or wti is None or wti.empty:
        raise RuntimeError("yfinance intraday returned empty")

    df = pd.DataFrame(
        {
            "Brent": brent["Close"],
            "WTI": wti["Close"],
        }
    )
    # Align on shared timestamps; 1-min bars sometimes miss one side
    df = df.dropna(how="any")
    if df.empty:
        raise RuntimeError("no overlapping intraday bars")
    df.index.name = "Datetime"
    return df


def health_check(timeout: float = 6.0) -> dict:
    """Return a health dict: probes a 1-day window for BZ=F."""
    if yf is None:
        return {"ok": False, "latency_ms": 0, "note": "yfinance not installed"}
    import time
    t0 = time.monotonic()
    try:
        t = yf.Ticker("BZ=F")
        hist = t.history(period="2d", interval="1d", auto_adjust=False)
        ok = hist is not None and not hist.empty
        return {
            "ok": bool(ok),
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": "" if ok else "empty response",
        }
    except Exception as exc:
        return {"ok": False, "latency_ms": int((time.monotonic() - t0) * 1000), "note": repr(exc)[:120]}
