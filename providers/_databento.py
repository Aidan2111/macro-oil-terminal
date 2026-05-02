"""Databento Brent/WTI provider (issue #105).

Subscribed via ``DATABENTO_API_KEY``. Wires Databento as the primary
intraday pricing source so the spread thesis runs against real-time
ticks instead of yfinance's 15-min-delayed feed. yfinance remains the
fallback when the env var is unset or the SDK / client errors.

Datasets:

  * GLBX.MDP3 — CME Globex Market Data 3 — for ``CL`` (WTI front-month)
  * IFEU.IMPACT — ICE Europe — for ``BZ`` (Brent front-month)

Both are available on the Databento "Stocks Starter + Futures" tier
the issue body called out (~$29-79/mo depending on add-ons; cost
audit lives in ``docs/quant/data-costs.md``).

The module is best-effort: a missing SDK or unset key raises
``RuntimeError`` so the orchestrator in ``providers/pricing.py`` can
fall through cleanly. We never crash the whole process.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd


_DEFAULT_LOOKBACK_DAYS = 60


def _client():
    """Lazy SDK import + key gate so the absence of the optional
    ``databento`` package only fails when this provider is actually
    invoked."""
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        raise RuntimeError("DATABENTO_API_KEY not set")
    try:
        import databento as db  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "databento SDK not installed; pip install databento"
        ) from exc
    return db.Historical(key=api_key)


def fetch_intraday(
    *,
    symbols: tuple[str, str] = ("CL.FUT", "BZ.FUT"),
    interval: str = "1m",
    lookback_days: int = 1,
) -> pd.DataFrame:
    """Return a wide-format frame indexed by ts_event with WTI + Brent close.

    Columns: ``WTI``, ``Brent``, ``Spread`` (Brent - WTI), all USD/bbl.

    The fetch goes through Databento's historical API at minute
    granularity. Realtime tick subscriptions follow the same pattern
    via ``Live`` rather than ``Historical`` — leave that wiring to a
    follow-up once the API key is provisioned.
    """
    client = _client()

    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(days=lookback_days)

    cl_dataset = "GLBX.MDP3"
    bz_dataset = "IFEU.IMPACT"

    cl = _fetch_continuous_ohlcv(client, cl_dataset, symbols[0], start, end, interval)
    bz = _fetch_continuous_ohlcv(client, bz_dataset, symbols[1], start, end, interval)

    df = pd.DataFrame(
        {"WTI": cl, "Brent": bz}
    ).dropna()
    if df.empty:
        raise RuntimeError(
            "Databento: no overlapping CL/BZ minute bars in the requested window"
        )
    df["Spread"] = df["Brent"] - df["WTI"]
    df.index.name = "Date"
    return df


def _fetch_continuous_ohlcv(
    client, dataset: str, symbol: str, start, end, interval: str,
) -> pd.Series:
    """Pull minute (or other-granularity) close prices for the
    front-month continuous contract.

    Wraps Databento's ``timeseries.get_range`` with a rolling-front
    schedule so the series is continuous across roll dates.
    """
    schema = "ohlcv-1m" if interval == "1m" else f"ohlcv-{interval}"
    data = client.timeseries.get_range(
        dataset=dataset,
        symbols=[symbol],
        stype_in="continuous",
        schema=schema,
        start=start,
        end=end,
    )
    df = data.to_df() if hasattr(data, "to_df") else pd.DataFrame(data)
    if df.empty:
        raise RuntimeError(f"Databento: empty {schema} for {symbol}")
    if "close" not in df.columns:
        raise RuntimeError(f"Databento: schema missing close column for {symbol}")
    s = pd.Series(df["close"].astype(float).to_numpy(), index=pd.to_datetime(df.index))
    s.name = symbol
    return s


def fetch_daily(years: int = 5) -> pd.DataFrame:
    """Daily close series — uses ``ohlcv-1d`` aggregations on the same
    continuous contracts."""
    client = _client()

    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(days=int(years * 365))

    cl = _fetch_continuous_ohlcv(client, "GLBX.MDP3", "CL.FUT", start, end, "1d")
    bz = _fetch_continuous_ohlcv(client, "IFEU.IMPACT", "BZ.FUT", start, end, "1d")
    df = pd.DataFrame({"WTI": cl, "Brent": bz}).dropna()
    if df.empty:
        raise RuntimeError("Databento: empty daily frame for CL/BZ")
    df["Spread"] = df["Brent"] - df["WTI"]
    df.index.name = "Date"
    return df


__all__ = ["fetch_intraday", "fetch_daily"]
