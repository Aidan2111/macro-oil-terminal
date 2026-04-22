"""3-2-1 crack spread helpers (refining margin proxy).

The 3-2-1 crack = (2·RBOB + HO) / 3  −  WTI, all in USD/bbl. When it's
blown out, US refiners are lifting domestic crude hard and WTI firms
versus Brent — so a moving crack is often the *cause* of Brent-WTI
dislocation. Feeding current crack + 30-day rolling correlation vs
Brent-WTI into the thesis context lets the LLM cite refining economics
explicitly.

Pricing comes from the same yfinance layer we already trust (15-min
delayed futures). RBOB and HO quotes are in USD per **gallon**, so we
scale by 42 (gallons per barrel) before computing the crack.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd


GAL_PER_BBL = 42.0


@dataclass
class CrackResult:
    ok: bool
    latest_crack_usd: float        # current 3-2-1 crack in USD/bbl
    latest_rbob_usd_per_gal: float
    latest_ho_usd_per_gal: float
    latest_wti_usd: float
    corr_30d_vs_brent_wti: float   # rolling-30d correlation of Δcrack vs Δ(Brent-WTI)
    series: Optional[pd.DataFrame] # full frame (Date, RBOB, HO, WTI, Crack)
    note: str = ""


def _load(tickers, years=1):
    """Thin wrapper over yfinance.download; returns a Close-only DataFrame."""
    try:
        import yfinance as yf
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"yfinance unavailable: {exc!r}")

    end = datetime.utcnow()
    start = end - timedelta(days=int(years * 365))
    raw = yf.download(
        tickers=tickers,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        group_by="column",
        threads=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned empty frame for crack tickers")

    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw["Adj Close"]
    else:
        close = raw[["Close"]] if "Close" in raw.columns else raw

    # Forward-fill weekends so the daily index is clean
    full_idx = pd.date_range(close.index.min(), close.index.max(), freq="D")
    return close.reindex(full_idx).ffill().bfill()


def compute_crack(
    brent_wti_daily: Optional[pd.DataFrame] = None,
    *,
    years: int = 1,
    rbob: str = "RB=F",
    ho: str = "HO=F",
    wti: str = "CL=F",
) -> CrackResult:
    """Compute the 3-2-1 crack series + 30d corr vs the Brent-WTI spread.

    Pass in ``brent_wti_daily`` (DataFrame with Brent, WTI columns) so we
    reuse the already-fetched pricing and skip a yfinance round-trip.
    If ``None`` we pull CL=F fresh as the WTI leg.
    """
    try:
        raw = _load([rbob, ho, wti], years=years)
    except Exception as exc:
        return CrackResult(
            ok=False, latest_crack_usd=float("nan"),
            latest_rbob_usd_per_gal=float("nan"),
            latest_ho_usd_per_gal=float("nan"),
            latest_wti_usd=float("nan"),
            corr_30d_vs_brent_wti=float("nan"),
            series=None,
            note=f"yfinance load failed: {exc!r}"[:200],
        )
    rbob_s = raw.get(rbob)
    ho_s = raw.get(ho)
    wti_s = raw.get(wti)
    if rbob_s is None or ho_s is None or wti_s is None:
        return CrackResult(
            ok=False, latest_crack_usd=float("nan"),
            latest_rbob_usd_per_gal=float("nan"),
            latest_ho_usd_per_gal=float("nan"),
            latest_wti_usd=float("nan"),
            corr_30d_vs_brent_wti=float("nan"),
            series=None,
            note="missing ticker in yfinance response",
        )

    df = pd.DataFrame(
        {
            "RBOB_usd_per_gal": rbob_s.astype(float),
            "HO_usd_per_gal": ho_s.astype(float),
            "WTI_usd": wti_s.astype(float),
        }
    )
    df["Crack_321_usd"] = (
        (2.0 * df["RBOB_usd_per_gal"] + df["HO_usd_per_gal"]) / 3.0
    ) * GAL_PER_BBL - df["WTI_usd"]

    corr_30d = float("nan")
    if brent_wti_daily is not None and not brent_wti_daily.empty:
        try:
            bw_spread = (
                brent_wti_daily["Brent"].astype(float) - brent_wti_daily["WTI"].astype(float)
            )
            # Align on shared dates
            aligned = pd.concat(
                {"crack": df["Crack_321_usd"], "bw": bw_spread}, axis=1
            ).dropna()
            if len(aligned) > 32:
                d_crack = aligned["crack"].diff()
                d_bw = aligned["bw"].diff()
                corr_30d = float(d_crack.tail(30).corr(d_bw.tail(30)))
        except Exception:
            corr_30d = float("nan")

    return CrackResult(
        ok=True,
        latest_crack_usd=float(df["Crack_321_usd"].iloc[-1]),
        latest_rbob_usd_per_gal=float(df["RBOB_usd_per_gal"].iloc[-1]),
        latest_ho_usd_per_gal=float(df["HO_usd_per_gal"].iloc[-1]),
        latest_wti_usd=float(df["WTI_usd"].iloc[-1]),
        corr_30d_vs_brent_wti=corr_30d,
        series=df,
    )


__all__ = ["CrackResult", "compute_crack", "GAL_PER_BBL"]
