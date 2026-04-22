"""CFTC Commitments of Traders (COT) — WTI positioning provider.

CFTC publishes the **disaggregated** futures-only COT report every Friday
at 15:30 ET. We read the year-to-date zipped CSV (``fut_disagg_txt_YYYY.zip``)
and extract positioning for the NYMEX WTI main contract.

The historical file is small enough (a few MB) and updates once a week,
so we cache the parsed frame in-process for 24h.

Contract of interest
--------------------
The disaggregated report lists NYMEX WTI as:

    "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"

(previously labelled "CRUDE OIL, LIGHT SWEET"). Open interest ~2M contracts.

Categories returned (All = combined futures, all contract months)
-----------------------------------------------------------------
  * ``producer_net`` — Producer / Merchant / Processor / User (physical hedger)
  * ``swap_net``     — Swap Dealer (bank flow, often offset producer hedges)
  * ``mm_net``       — Managed Money (hedge funds, the "smart money"
                       but also the source of the biggest crowded trades)
  * ``other_rept_net`` — Other reportable (CTAs, prop shops)
  * ``nonrept_net``  — Small trader net

``_net`` = Long - Short (contracts, 1000 bbls each). Managed-Money net is
historically mean-reverting — extreme positive (crowded long) often
precedes reversal, extreme negative (crowded short) the inverse.
"""

from __future__ import annotations

import io
import os
import time
import zipfile
from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import requests


# Primary market name (exact match against "Market_and_Exchange_Names")
WTI_MARKET_NAME = "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"

# Accepted alternate names in case CFTC relabels again. The column match
# is checked in order — first hit wins.
_ACCEPTED_MARKET_NAMES: tuple[str, ...] = (
    "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
    "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
    "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",  # ICE WTI fallback
)


def _year_url(year: int) -> str:
    return f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"


# Module-level cache: (year, ...) -> (fetched_at, frame)
_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_TTL_SECONDS = 86_400  # 24h — COT publishes weekly on Fridays


def _fetch_year_frame(year: int, timeout: int = 20) -> pd.DataFrame:
    """Download one CFTC year zip and return a parsed DataFrame (all contracts)."""
    resp = requests.get(_year_url(year), timeout=timeout)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        # The zip always contains a single txt file — usually "f_year.txt" or "annual.txt".
        name = next((n for n in zf.namelist() if n.lower().endswith(".txt")), None)
        if name is None:
            raise RuntimeError(f"CFTC {year}: zip has no .txt entry")
        with zf.open(name) as fh:
            df = pd.read_csv(fh, low_memory=False)
    # The report-date column name has varied historically; normalise to "report_date".
    date_col = None
    for cand in (
        "Report_Date_as_YYYY-MM-DD",
        "As of Date in Form YYYY-MM-DD",
        "Report Date as YYYY-MM-DD",
    ):
        if cand in df.columns:
            date_col = cand
            break
    if date_col is None:
        raise RuntimeError(f"CFTC {year}: no recognised report-date column")
    df["report_date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["report_date"])
    return df


def _filter_wti(df: pd.DataFrame) -> pd.DataFrame:
    """Filter a full year-frame down to the WTI main contract rows."""
    name_col = "Market_and_Exchange_Names" if "Market_and_Exchange_Names" in df.columns else "Market and Exchange Names"
    if name_col not in df.columns:
        raise RuntimeError("CFTC frame missing market-name column")
    for accepted in _ACCEPTED_MARKET_NAMES:
        sub = df[df[name_col] == accepted].copy()
        if not sub.empty:
            sub["_matched_market"] = accepted
            return sub.sort_values("report_date")
    raise RuntimeError("CFTC: no WTI rows found in any accepted market name")


def _compute_net_positions(wti: pd.DataFrame) -> pd.DataFrame:
    """Compute per-week net positions for each trader category. Returns a tidy frame."""
    # Column aliases — the disaggregated schema uses underscores.
    L = {
        "producer":   "Prod_Merc_Positions_Long_All",
        "swap":       "Swap_Positions_Long_All",
        "mm":         "M_Money_Positions_Long_All",
        "other_rept": "Other_Rept_Positions_Long_All",
        "nonrept":    "NonRept_Positions_Long_All",
    }
    S = {
        "producer":   "Prod_Merc_Positions_Short_All",
        "swap":       "Swap__Positions_Short_All",  # note double underscore in CFTC schema
        "mm":         "M_Money_Positions_Short_All",
        "other_rept": "Other_Rept_Positions_Short_All",
        "nonrept":    "NonRept_Positions_Short_All",
    }
    rows: list[dict] = []
    for _, r in wti.iterrows():
        row = {
            "date": r["report_date"],
            "open_interest": int(r.get("Open_Interest_All", 0) or 0),
            "market": r.get("_matched_market", ""),
        }
        for cat in L:
            long_col = L[cat]
            short_col = S[cat]
            if long_col not in r or short_col not in r:
                continue
            try:
                lo = float(r[long_col])
                sh = float(r[short_col])
            except Exception:
                continue
            row[f"{cat}_long"] = int(lo)
            row[f"{cat}_short"] = int(sh)
            row[f"{cat}_net"] = int(lo - sh)
        rows.append(row)
    out = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    out = out.set_index("date")
    out.index = pd.DatetimeIndex(out.index, name="date")
    return out


@dataclass
class COTResult:
    frame: pd.DataFrame
    source_url: str
    fetched_at: pd.Timestamp
    market_name: str
    weeks: int


def fetch_wti_positioning(years: Iterable[int] | None = None) -> COTResult:
    """Return a weekly COT positioning frame for NYMEX WTI.

    Pulls ``years`` of zipped CFTC history (defaults to current + previous
    two years so percentile/Z-scores have ~3y of context). Results are
    cached in-process for 24h keyed by the set of years requested.
    """
    if years is None:
        today = pd.Timestamp.utcnow()
        years = (today.year - 2, today.year - 1, today.year)
    years = tuple(sorted(set(int(y) for y in years)))
    cache_key = ",".join(str(y) for y in years)
    now = time.time()
    hit = _CACHE.get(cache_key)
    if hit is not None and now - hit[0] < _TTL_SECONDS:
        cached = hit[1]
        return COTResult(
            frame=cached,
            source_url=_year_url(years[-1]),
            fetched_at=pd.Timestamp.utcfromtimestamp(hit[0]),
            market_name=cached["market"].iloc[-1] if not cached.empty else "",
            weeks=len(cached),
        )

    parts: list[pd.DataFrame] = []
    for y in years:
        try:
            raw = _fetch_year_frame(y)
            parts.append(_filter_wti(raw))
        except Exception:
            # Individual year failures are tolerable — continue with whatever succeeded.
            continue
    if not parts:
        raise RuntimeError(f"CFTC: no WTI data retrieved across {years}")
    all_wti = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["report_date"]).sort_values("report_date")
    net = _compute_net_positions(all_wti)
    _CACHE[cache_key] = (now, net)
    return COTResult(
        frame=net,
        source_url=_year_url(years[-1]),
        fetched_at=pd.Timestamp.utcnow(),
        market_name=net["market"].iloc[-1] if not net.empty else "",
        weeks=len(net),
    )


def managed_money_zscore(frame: pd.DataFrame, lookback_weeks: int = 156) -> float | None:
    """Z-score of the latest Managed Money net position vs trailing lookback.

    ``lookback_weeks`` defaults to ~3y. Returns None if the series is too short.
    """
    if frame is None or frame.empty or "mm_net" not in frame.columns:
        return None
    s = frame["mm_net"].dropna().tail(lookback_weeks)
    if len(s) < 20:
        return None
    mean = float(s.mean())
    std = float(s.std(ddof=0))
    if std <= 0:
        return None
    latest = float(s.iloc[-1])
    return (latest - mean) / std


def health_check(timeout: float = 6.0) -> dict:
    """Liveness probe — HEAD on the current-year zip."""
    t0 = time.monotonic()
    try:
        today = pd.Timestamp.utcnow()
        resp = requests.head(_year_url(today.year), timeout=timeout, allow_redirects=True)
        ok = resp.status_code == 200
        return {
            "ok": bool(ok),
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": f"HEAD {resp.status_code}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": f"exc: {repr(exc)[:120]}",
        }


__all__ = [
    "WTI_MARKET_NAME",
    "COTResult",
    "fetch_wti_positioning",
    "managed_money_zscore",
    "health_check",
]
