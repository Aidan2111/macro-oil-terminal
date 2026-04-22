"""FRED API inventory provider (requires FRED_API_KEY).

If the env var ``FRED_API_KEY`` is set, this provider fetches
WCESTUS1 (weekly U.S. ending stocks of crude oil excl. SPR) and
WCSSTUS1 (SPR stocks) via the St. Louis Fed observations API.

FRED dropped keyless CSV downloads via fredgraph.csv (now 404 for
petroleum series), so this path is explicitly key-gated. Register
a free key at https://fred.stlouisfed.org/docs/api/api_key.html.
"""

from __future__ import annotations

import os
from typing import Iterable

import pandas as pd
import requests


_API = "https://api.stlouisfed.org/fred/series/observations"


def _fetch_series(series_id: str, start: str = "2018-01-01") -> pd.Series:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("FRED_API_KEY not set")
    resp = requests.get(
        _API,
        params={
            "series_id": series_id,
            "observation_start": start,
            "api_key": api_key,
            "file_type": "json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    obs = data.get("observations", [])
    if not obs:
        raise RuntimeError(f"FRED {series_id}: no observations")
    idx = pd.DatetimeIndex([pd.Timestamp(o["date"]) for o in obs])
    vals = [float(o["value"]) if o["value"] not in (".", "") else float("nan") for o in obs]
    return pd.Series(vals, index=idx).dropna() * 1_000.0  # Mbbl -> bbls


def fetch_inventory(start: str = "2018-01-01") -> pd.DataFrame:
    commercial = _fetch_series("WCESTUS1", start=start)
    try:
        spr = _fetch_series("WCSSTUS1", start=start)
    except Exception:
        spr = pd.Series(dtype=float)

    df = pd.concat(
        {"Commercial_bbls": commercial, "SPR_bbls": spr}, axis=1
    ).sort_index()
    df["SPR_bbls"] = df["SPR_bbls"].ffill()
    df["Commercial_bbls"] = df["Commercial_bbls"].ffill()
    df = df.dropna(subset=["Commercial_bbls"])
    df["Total_Inventory_bbls"] = df["Commercial_bbls"].fillna(0) + df["SPR_bbls"].fillna(0)
    df.index.name = "Date"
    return df
