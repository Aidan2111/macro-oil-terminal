"""EIA inventory provider — prefers the v2 API when ``EIA_API_KEY`` is set,
falls back to the keyless dnav LeafHandler scrape otherwise.

Series used:
  * WCESTUS1            — weekly U.S. commercial crude oil ending stocks (Mbbl)
  * WCSSTUS1            — weekly SPR stocks (Mbbl)
  * W_EPC0_SAX_YCUOK_MBBL — weekly Cushing, OK crude stocks (Mbbl)

Values are returned in **barrels** (EIA publishes thousand barrels;
we multiply by 1000 for consistency with the rest of the terminal).

Primary path (v2 API, key-gated):
    https://api.eia.gov/v2/seriesid/<series>?api_key=<key>

Fallback path (keyless HTML scrape):
    https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=pet&s=<series>&f=W

The v2 endpoint is faster, json-native, and rate-limit-stable. The
dnav fallback is kept as a belt-and-suspenders path for the open-source
deploy with no key configured.
"""

from __future__ import annotations

import os
import time
from io import StringIO
from typing import Tuple

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Series IDs
# ---------------------------------------------------------------------------
_SERIES_COMMERCIAL = "WCESTUS1"
_SERIES_SPR = "WCSSTUS1"
# Cushing, OK delivery hub — primary driver of the WTI leg of the Brent-WTI spread.
_SERIES_CUSHING = "W_EPC0_SAX_YCUOK_MBBL"

# ---------------------------------------------------------------------------
# v2 API
# ---------------------------------------------------------------------------
_V2_BASE = "https://api.eia.gov/v2/seriesid/{series}"

# Lightweight in-process cache: series -> (fetched_at_ts, series)
_V2_CACHE: dict[str, tuple[float, pd.Series]] = {}
_V2_TTL_SECONDS = 60 * 60  # 1 hour — weekly data, no need to hammer the API


def _v2_series_id(bare: str) -> str:
    """Normalise a bare EIA series code to the v2 API path form.

    The v2 API expects ``PET.<SERIES>.W`` for weekly petroleum series. The
    dnav LeafHandler accepts the bare code alone. We keep the bare code
    as the canonical internal ID and only transform at the v2 boundary.
    """
    if bare.startswith("PET."):
        return bare
    return f"PET.{bare}.W"


def _fetch_series_v2(series_id: str, timeout: int = 15) -> pd.Series:
    """Fetch a single EIA series via the v2 API (requires EIA_API_KEY)."""
    api_key = os.environ.get("EIA_API_KEY")
    if not api_key:
        raise RuntimeError("EIA_API_KEY not set")

    now = time.time()
    hit = _V2_CACHE.get(series_id)
    if hit is not None and now - hit[0] < _V2_TTL_SECONDS:
        return hit[1]

    resp = requests.get(
        _V2_BASE.format(series=_v2_series_id(series_id)),
        params={"api_key": api_key},
        timeout=timeout,
    )
    if resp.status_code == 403:
        raise RuntimeError(f"EIA v2: 403 forbidden (bad key?) for {series_id}")
    resp.raise_for_status()
    payload = resp.json()
    data = (payload.get("response") or {}).get("data") or []
    if not data:
        raise RuntimeError(f"EIA v2: empty data for {series_id}")

    idx = pd.to_datetime([row.get("period") for row in data], errors="coerce")
    vals = pd.to_numeric([row.get("value") for row in data], errors="coerce")
    s = pd.Series(vals, index=idx, name=series_id).dropna()
    s = s[~s.index.isna()].sort_index()
    if s.empty:
        raise RuntimeError(f"EIA v2: zero valid rows for {series_id}")
    # EIA publishes thousand barrels -> convert to barrels
    s = s * 1_000.0
    _V2_CACHE[series_id] = (now, s)
    return s


# ---------------------------------------------------------------------------
# dnav fallback (keyless HTML scrape)
# ---------------------------------------------------------------------------
_DNAV_BASE = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=pet&s={series}&f=W"


def _fetch_dnav(series: str, timeout: int = 15) -> pd.Series:
    """Return a weekly pd.Series for the given EIA dnav series ID (barrels)."""
    url = _DNAV_BASE.format(series=series)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    tables = pd.read_html(StringIO(resp.text))
    table = None
    for t in tables:
        if t.shape[1] >= 11 and t.shape[0] >= 100:
            table = t
            break
    if table is None:
        raise RuntimeError(f"EIA dnav: could not locate data table for {series}")

    if isinstance(table.columns, pd.MultiIndex):
        flat = [
            " ".join(str(c).strip() for c in tup if c and "Unnamed" not in str(c)).strip()
            for tup in table.columns
        ]
        table.columns = flat

    records: list[tuple[pd.Timestamp, float]] = []
    for _, row in table.iterrows():
        ym = str(row.get("Year-Month") or row.iloc[0])
        if not ym or "Year-Month" in ym:
            continue
        try:
            year = int(ym.split("-")[0])
        except Exception:
            continue
        for w in range(1, 6):
            date_col = f"Week {w} End Date"
            val_col = f"Week {w} Value"
            if date_col not in table.columns or val_col not in table.columns:
                continue
            date_cell = row.get(date_col)
            val_cell = row.get(val_col)
            if pd.isna(date_cell) or pd.isna(val_cell):
                continue
            date_str = str(date_cell).strip()
            if "/" not in date_str:
                continue
            mm, dd = date_str.split("/")[:2]
            try:
                dt = pd.Timestamp(year=year, month=int(mm), day=int(dd))
            except Exception:
                continue
            try:
                val = float(val_cell)
            except Exception:
                continue
            records.append((dt, val))

    if not records:
        raise RuntimeError(f"EIA dnav: parsed zero rows for {series}")

    series_obj = pd.Series(
        [v for _, v in records],
        index=pd.DatetimeIndex([d for d, _ in records], name="Date"),
    ).sort_index()
    series_obj = series_obj[~series_obj.index.duplicated(keep="last")]
    return series_obj * 1_000.0


# ---------------------------------------------------------------------------
# Unified fetcher: v2 first, then dnav
# ---------------------------------------------------------------------------
def _fetch_series(series_id: str) -> pd.Series:
    if os.environ.get("EIA_API_KEY"):
        try:
            return _fetch_series_v2(series_id)
        except Exception:
            # Silent fallback — dnav path is still correct data
            pass
    return _fetch_dnav(series_id)


def fetch_series_v2(series_id: str) -> Tuple[pd.DatetimeIndex, pd.Series]:
    """Public helper: ``(dates, values)`` tuple for a single series.

    Prefers the v2 API when EIA_API_KEY is set; otherwise falls through
    to the keyless dnav path.
    """
    s = _fetch_series(series_id)
    return s.index, s


def fetch_cushing(start: str | None = "2018-01-01") -> pd.Series:
    """Weekly Cushing, OK crude stocks (barrels)."""
    s = _fetch_series(_SERIES_CUSHING)
    if start is not None:
        try:
            s = s[s.index >= pd.Timestamp(start)]
        except Exception:
            pass
    s.name = "Cushing_bbls"
    return s


def fetch_inventory(start: str | None = "2018-01-01") -> pd.DataFrame:
    """Return a DataFrame with columns Commercial_bbls, SPR_bbls, Cushing_bbls,
    Total_Inventory_bbls. Uses v2 API when EIA_API_KEY is set; dnav otherwise.
    """
    commercial = _fetch_series(_SERIES_COMMERCIAL)
    try:
        spr = _fetch_series(_SERIES_SPR)
    except Exception:
        spr = pd.Series(dtype=float)
    try:
        cushing = _fetch_series(_SERIES_CUSHING)
    except Exception:
        cushing = pd.Series(dtype=float)

    df = pd.concat(
        {
            "Commercial_bbls": commercial,
            "SPR_bbls": spr,
            "Cushing_bbls": cushing,
        },
        axis=1,
    )
    df = df.sort_index()
    df["SPR_bbls"] = df["SPR_bbls"].ffill()
    df["Commercial_bbls"] = df["Commercial_bbls"].ffill()
    df["Cushing_bbls"] = df["Cushing_bbls"].ffill()

    if start is not None:
        try:
            df = df[df.index >= pd.Timestamp(start)]
        except Exception:
            pass

    df["Total_Inventory_bbls"] = df["Commercial_bbls"].fillna(0) + df["SPR_bbls"].fillna(0)
    df = df.dropna(subset=["Commercial_bbls"])
    df.index.name = "Date"
    return df


def active_mode() -> str:
    """Return a human-readable tag of which path is active."""
    return "EIA v2 API (keyed)" if os.environ.get("EIA_API_KEY") else "EIA dnav (keyless)"


def health_check(timeout: float = 6.0) -> dict:
    """Liveness probe — prefers v2 API when key is set, else dnav."""
    t0 = time.monotonic()
    if os.environ.get("EIA_API_KEY"):
        try:
            resp = requests.get(
                _V2_BASE.format(series=_v2_series_id(_SERIES_COMMERCIAL)),
                params={"api_key": os.environ["EIA_API_KEY"]},
                timeout=timeout,
            )
            ok = resp.status_code == 200 and bool(
                (resp.json().get("response") or {}).get("data")
            )
            return {
                "ok": bool(ok),
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "note": f"v2 status={resp.status_code}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "note": f"v2 exc: {repr(exc)[:120]}",
            }
    try:
        resp = requests.get(
            _DNAV_BASE.format(series=_SERIES_COMMERCIAL),
            timeout=timeout,
        )
        ok = resp.status_code == 200 and len(resp.text) > 10_000
        return {
            "ok": bool(ok),
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": f"dnav status={resp.status_code}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": f"dnav exc: {repr(exc)[:120]}",
        }


__all__ = [
    "fetch_series_v2",
    "fetch_cushing",
    "fetch_inventory",
    "fetch_steo_series",
    "active_mode",
    "health_check",
]


# ---------------------------------------------------------------------------
# STEO (Short-Term Energy Outlook) — issue #79
# ---------------------------------------------------------------------------
#
# Iran crude oil production is published as a monthly STEO series at:
#   https://api.eia.gov/v2/steo/data/
#       ?frequency=monthly&data[0]=value
#       &facets[seriesId][]=COPR_IR
#       &api_key=<key>
#
# The series ID we care about is `COPR_IR` (Iran Crude Oil Production,
# Monthly, thousand bbl/day). Other STEO series share the same shape so
# the helper takes the bare ID and is generic.
#
# STEO is monthly; we cache for 24h. EIA publishes new STEO releases on
# the 2nd Tuesday of each month — well within the cache window.

_STEO_BASE = "https://api.eia.gov/v2/steo/data/"
_STEO_TTL_SECONDS = 60 * 60 * 24  # 24 h
_STEO_CACHE: dict[str, tuple[float, list[dict]]] = {}


def fetch_steo_series(
    series_id: str = "COPR_IR",
    *,
    timeout: int = 15,
    limit: int = 60,
) -> list[dict]:
    """Fetch the monthly STEO series for `series_id`.

    Returns a list of `{"month": "YYYY-MM", "value": float}` rows
    sorted ascending by month, oldest → newest. Returns the most recent
    `limit` rows.

    Raises RuntimeError on any upstream failure (caller surfaces 503).
    """
    api_key = os.environ.get("EIA_API_KEY")
    if not api_key:
        raise RuntimeError("EIA_API_KEY not set — STEO requires the v2 API key")

    now = time.time()
    hit = _STEO_CACHE.get(series_id)
    if hit is not None and now - hit[0] < _STEO_TTL_SECONDS:
        return hit[1][-limit:]

    resp = requests.get(
        _STEO_BASE,
        params={
            "frequency": "monthly",
            "data[0]": "value",
            "facets[seriesId][]": series_id,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": str(limit),
            "api_key": api_key,
        },
        timeout=timeout,
    )
    if resp.status_code == 403:
        raise RuntimeError(f"EIA STEO: 403 forbidden for {series_id}")
    resp.raise_for_status()
    payload = resp.json()
    data = (payload.get("response") or {}).get("data") or []
    if not data:
        raise RuntimeError(f"EIA STEO: empty data for {series_id}")

    rows: list[dict] = []
    for r in data:
        period = r.get("period")
        value = r.get("value")
        if period is None or value is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        # Period from STEO is "YYYY-MM"; pass through unchanged.
        rows.append({"month": str(period), "value": v})
    if not rows:
        raise RuntimeError(f"EIA STEO: zero valid rows for {series_id}")
    rows.sort(key=lambda r: r["month"])
    _STEO_CACHE[series_id] = (now, rows)
    return rows[-limit:]
