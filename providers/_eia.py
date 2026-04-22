"""EIA dnav LeafHandler-based inventory provider.

Real, key-less, government-published weekly crude oil stocks. Parses the
HTML table returned by:
    https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=pet&s=<SERIES>&f=W

Series used:
  * WCESTUS1 — weekly U.S. ending stocks excluding SPR of crude oil (Mbbl)
  * WCSSTUS1 — weekly U.S. crude oil stocks in the Strategic Petroleum Reserve (Mbbl)

Values are returned in **barrels** (the EIA publishes thousand barrels;
we multiply by 1000 for consistency with the rest of the terminal).
"""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from typing import Tuple

import pandas as pd
import requests


_BASE = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=pet&s={series}&f=W"
_SERIES_COMMERCIAL = "WCESTUS1"
_SERIES_SPR = "WCSSTUS1"
# Cushing, OK delivery hub — primary driver of the WTI leg of the Brent-WTI spread.
_SERIES_CUSHING = "W_EPC0_SAX_YCUOK_MBBL"


def _fetch_dnav(series: str, timeout: int = 15) -> pd.Series:
    """Return a weekly pd.Series for the given EIA dnav series ID."""
    url = _BASE.format(series=series)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    tables = pd.read_html(StringIO(resp.text))
    # The wide Year-Month × Week table is the biggest one. Find it.
    table = None
    for t in tables:
        if t.shape[1] >= 11 and t.shape[0] >= 100:
            table = t
            break
    if table is None:
        raise RuntimeError(f"EIA dnav: could not locate data table for {series}")

    # Flatten MultiIndex columns (Year-Month, Week 1 End Date, Week 1 Value, ...)
    if isinstance(table.columns, pd.MultiIndex):
        flat = [" ".join(str(c).strip() for c in tup if c and "Unnamed" not in str(c)).strip() for tup in table.columns]
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
            # date_cell like "MM/DD"
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
    # Drop duplicate dates (paranoid — shouldn't happen)
    series_obj = series_obj[~series_obj.index.duplicated(keep="last")]
    # EIA publishes thousand barrels -> convert to barrels
    return series_obj * 1_000.0


def fetch_cushing(start: str | None = "2018-01-01") -> pd.Series:
    """Weekly Cushing, OK crude stocks (barrels). Keyless EIA dnav.

    Cushing is the physical delivery point for the WTI contract. Its
    utilisation is the dominant driver of the WTI leg of the Brent-WTI
    spread — far more predictive than total US inventory.
    """
    s = _fetch_dnav(_SERIES_CUSHING)
    if start is not None:
        try:
            s = s[s.index >= pd.Timestamp(start)]
        except Exception:
            pass
    s.name = "Cushing_bbls"
    return s


def fetch_inventory(start: str | None = "2018-01-01") -> pd.DataFrame:
    """Return a DataFrame with columns Commercial_bbls, SPR_bbls, Cushing_bbls, Total_Inventory_bbls.

    Commercial, SPR, and Cushing all come from the EIA dnav LeafHandler
    endpoint — no API key.
    """
    commercial = _fetch_dnav(_SERIES_COMMERCIAL)
    try:
        spr = _fetch_dnav(_SERIES_SPR)
    except Exception:
        spr = pd.Series(dtype=float)
    try:
        cushing = _fetch_dnav(_SERIES_CUSHING)
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
