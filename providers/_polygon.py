"""Polygon.io pricing provider — tertiary, key-gated.

Free tier: 5 calls/minute, 15-minute delayed. Symbols for crude
futures: ``C:BRN1!`` (Brent) / ``C:WTI1!`` (WTI) on the REST v2
aggregates endpoint. Keyed on ``POLYGON_API_KEY``.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests


_BASE = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{frm}/{to}"


def _api_key() -> Optional[str]:
    return os.environ.get("POLYGON_API_KEY")


def _fetch(ticker: str, frm: str, to: str) -> pd.Series:
    key = _api_key()
    if not key:
        raise RuntimeError("POLYGON_API_KEY not set")
    url = _BASE.format(ticker=ticker, frm=frm, to=to)
    resp = requests.get(url, params={"apiKey": key, "adjusted": "true", "limit": 50000}, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") == "ERROR" or "results" not in body:
        raise RuntimeError(f"polygon.io error: {body.get('error') or body.get('status')}")
    rows = body.get("results") or []
    if not rows:
        raise RuntimeError(f"polygon.io: zero rows for {ticker}")
    idx = pd.to_datetime([r["t"] for r in rows], unit="ms", utc=False)
    vals = [float(r["c"]) for r in rows]
    return pd.Series(vals, index=idx, name=ticker).sort_index()


def fetch_daily(years: int = 5, brent_ticker: str = "C:BRN1!", wti_ticker: str = "C:WTI1!") -> pd.DataFrame:
    end = datetime.now(timezone.utc).replace(tzinfo=None).date()
    start = end - timedelta(days=int(years * 365))
    brent = _fetch(brent_ticker, start.isoformat(), end.isoformat())
    wti = _fetch(wti_ticker, start.isoformat(), end.isoformat())
    df = pd.concat({"Brent": brent, "WTI": wti}, axis=1).dropna()
    if df.empty:
        raise RuntimeError("polygon.io: no overlapping Brent/WTI bars")
    df.index.name = "Date"
    return df


def health_check(timeout: float = 6.0) -> dict:
    key = _api_key()
    if not key:
        return {"ok": False, "latency_ms": 0, "note": "no api key set"}
    import time
    t0 = time.monotonic()
    try:
        resp = requests.get(
            "https://api.polygon.io/v3/reference/tickers",
            params={"apiKey": key, "limit": 1},
            timeout=timeout,
        )
        ok = resp.status_code == 200
        return {
            "ok": bool(ok),
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": "" if ok else f"status={resp.status_code}",
        }
    except Exception as exc:
        return {"ok": False, "latency_ms": int((time.monotonic() - t0) * 1000), "note": repr(exc)[:120]}


__all__ = ["fetch_daily", "health_check"]
