"""Pricing provider orchestrator — daily + intraday.

Primary: yfinance (BZ=F, CL=F). Intraday is 1-min with ~15min publisher
delay on futures.

Optional: Twelve Data (``TWELVEDATA_API_KEY``) — if set, preferred for
intraday because of cleaner tick alignment. Implementation stub is
provided; wire it in when a key lands.

No synthetic fallback: on total failure we raise ``PricingUnavailable``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd


class PricingUnavailable(RuntimeError):
    """Raised when no pricing provider could return a frame."""


@dataclass
class PricingResult:
    frame: pd.DataFrame
    source: str
    kind: str  # 'daily' or 'intraday'
    source_url: str
    fetched_at: pd.Timestamp


def fetch_pricing_daily(years: int = 5) -> PricingResult:
    """Try yfinance → Twelve Data → Polygon.io in order, each gated on availability."""
    errors: list[str] = []
    try:
        from . import _yfinance
        df = _yfinance.fetch_daily(years=years)
        return PricingResult(
            frame=df, source="yfinance", kind="daily",
            source_url="https://finance.yahoo.com/quote/BZ=F",
            fetched_at=pd.Timestamp.now(tz="UTC").tz_convert(None),
        )
    except Exception as exc:
        errors.append(f"yfinance: {exc!r}")

    if os.environ.get("TWELVE_DATA_API_KEY") or os.environ.get("TWELVEDATA_API_KEY"):
        try:
            from . import _twelvedata
            df = _twelvedata.fetch_daily(years=years)
            return PricingResult(
                frame=df, source="Twelve Data", kind="daily",
                source_url="https://twelvedata.com/",
                fetched_at=pd.Timestamp.now(tz="UTC").tz_convert(None),
            )
        except Exception as exc:
            errors.append(f"twelvedata: {exc!r}")

    if os.environ.get("POLYGON_API_KEY"):
        try:
            from . import _polygon
            df = _polygon.fetch_daily(years=years)
            return PricingResult(
                frame=df, source="Polygon.io", kind="daily",
                source_url="https://polygon.io/",
                fetched_at=pd.Timestamp.now(tz="UTC").tz_convert(None),
            )
        except Exception as exc:
            errors.append(f"polygon: {exc!r}")

    raise PricingUnavailable(
        "No pricing provider returned daily data:\n- " + "\n- ".join(errors)
    )


def fetch_pricing_intraday(interval: str = "1m", period: str = "2d") -> PricingResult:
    errors: list[str] = []
    try:
        from . import _yfinance
        df = _yfinance.fetch_intraday(interval=interval, period=period)
        return PricingResult(
            frame=df,
            source="yfinance",
            kind="intraday",
            source_url="https://finance.yahoo.com/quote/BZ=F",
            fetched_at=pd.Timestamp.now(tz="UTC").tz_convert(None),
        )
    except Exception as exc:
        errors.append(f"yfinance: {exc!r}")
    # Room for twelvedata.fetch_intraday when TWELVEDATA_API_KEY is set
    raise PricingUnavailable(
        "No pricing provider returned intraday data:\n- " + "\n- ".join(errors)
    )


def active_pricing_provider(kind: str) -> str:
    if os.environ.get("TWELVEDATA_API_KEY"):
        return f"Twelve Data ({kind}, keyed)  → yfinance fallback"
    return f"Yahoo Finance ({kind}, 15-min delayed futures)"
