"""Data ingestion for macro oil terminal.

Provides three primary loaders:
  * fetch_pricing_data()   – 5y daily Brent/WTI from yfinance
  * simulate_inventory()   – 2y US commercial + SPR inventory (downward trend)
  * generate_ais_mock()    – mock DataFrame of 500 crude tankers

All functions are defensive: they always return a valid pandas object,
even if the external call fails, so downstream code never sees None.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover – yfinance import should not fail at module load
    yf = None

warnings.filterwarnings("ignore", category=FutureWarning)


# ---------------------------------------------------------------------------
# 1. Pricing
# ---------------------------------------------------------------------------
def _synthetic_pricing(days: int = 5 * 365) -> pd.DataFrame:
    """Deterministic fallback pricing frame used when yfinance is unreachable."""
    end = datetime.utcnow().date()
    idx = pd.date_range(end=end, periods=days, freq="D")
    rng = np.random.default_rng(42)

    # Mean-reverting random walks around realistic long-run averages
    wti = np.cumsum(rng.normal(0, 0.6, size=days)) + 75.0
    brent_premium = 3.5 + np.cumsum(rng.normal(0, 0.05, size=days))
    brent = wti + brent_premium

    df = pd.DataFrame({"Brent": brent, "WTI": wti}, index=idx)
    df.index.name = "Date"
    return df


def fetch_pricing_data(years: int = 5) -> pd.DataFrame:
    """Return a daily DataFrame with columns ``Brent`` and ``WTI``.

    Uses yfinance (BZ=F, CL=F). Forward-fills any missing days and aligns
    both series to a shared daily DatetimeIndex. Always returns a populated
    DataFrame – falls back to a synthetic series if the network call fails.
    """
    if yf is None:
        return _synthetic_pricing(days=years * 365)

    end = datetime.utcnow()
    start = end - timedelta(days=years * 365)

    try:
        raw = yf.download(
            tickers=["BZ=F", "CL=F"],
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            group_by="column",
            threads=False,
        )
    except Exception:
        return _synthetic_pricing(days=years * 365)

    if raw is None or raw.empty:
        return _synthetic_pricing(days=years * 365)

    # yfinance returns a MultiIndex (field, ticker). Prefer 'Close' (or 'Adj Close').
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw["Adj Close"]
        else:
            close = raw[["Close"]] if "Close" in raw.columns else raw
    except Exception:
        return _synthetic_pricing(days=years * 365)

    close = close.rename(columns={"BZ=F": "Brent", "CL=F": "WTI"})
    # Ensure both columns exist; fall back to synthetic if not
    if "Brent" not in close.columns or "WTI" not in close.columns:
        return _synthetic_pricing(days=years * 365)

    df = close[["Brent", "WTI"]].copy()
    df.index = pd.to_datetime(df.index)
    # Daily re-index, forward-fill weekends/holidays
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full_idx).ffill().bfill()
    df.index.name = "Date"

    if df.isna().all().any() or len(df) < 30:
        return _synthetic_pricing(days=years * 365)

    return df


# ---------------------------------------------------------------------------
# 2. Inventory
# ---------------------------------------------------------------------------
def simulate_inventory(years: int = 2, seed: int = 7) -> pd.DataFrame:
    """Simulate a weekly total (commercial + SPR) US crude inventory series.

    Values are in *barrels* (not thousand barrels). Long-run trend is
    negative (net drawdown) with realistic weekly noise and a subtle
    seasonal wave.
    """
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(datetime.utcnow().date())
    weeks = max(8, years * 52)

    # Build the index first, then size every numeric array from len(idx).
    # pandas 2.x has been observed to return ``periods - 1`` entries when
    # ``end`` doesn't land on the weekly anchor, so don't assume the length.
    idx = pd.date_range(end=end, periods=weeks, freq="W-FRI")
    if len(idx) == 0:
        idx = pd.date_range(end=end, periods=max(weeks, 8), freq="7D")
    n = len(idx)

    # Start ~ 820 Mbbl (commercial ~430 + SPR ~390) – current-era realistic
    start_level = 820_000_000.0
    trend = np.linspace(0, -160_000_000.0, n)  # ~160 Mbbl drawdown over window
    seasonal = 18_000_000.0 * np.sin(np.linspace(0, 4 * np.pi, n))
    noise = rng.normal(0, 4_500_000.0, size=n)
    values = start_level + trend + seasonal + noise

    df = pd.DataFrame({"Total_Inventory_bbls": values}, index=idx)
    df.index.name = "Date"
    return df


# ---------------------------------------------------------------------------
# 3. AIS fleet mock
# ---------------------------------------------------------------------------
_FLAG_WEIGHTS = {
    "Panama": 0.22,
    "Liberia": 0.18,
    "United States": 0.14,
    "Iran": 0.10,
    "Russia": 0.10,
    "Marshall Islands": 0.08,
    "Malta": 0.06,
    "Greece": 0.05,
    "Venezuela": 0.04,
    "Singapore": 0.03,
}

_DESTINATIONS = [
    "Houston, US",
    "Corpus Christi, US",
    "Rotterdam, NL",
    "Singapore, SG",
    "Ningbo, CN",
    "Qingdao, CN",
    "Fujairah, AE",
    "Sikka, IN",
    "Sao Sebastiao, BR",
    "Primorsk, RU",
    "Kharg Island, IR",
    "Jose Terminal, VE",
    "St. James, US",
    "Long Beach, US",
    "Yokohama, JP",
]

_VESSEL_PREFIXES = [
    "SEA",
    "GULF",
    "PACIFIC",
    "ATLANTIC",
    "NORDIC",
    "ARCTIC",
    "DESERT",
    "IMPERIAL",
    "RED",
    "BLUE",
    "GOLDEN",
    "SILVER",
]
_VESSEL_SUFFIXES = [
    "VOYAGER",
    "PIONEER",
    "TRADER",
    "SPIRIT",
    "STAR",
    "HORIZON",
    "CROWN",
    "GLORY",
    "EXPRESS",
    "TITAN",
    "DAWN",
    "SENTINEL",
]


# Rough shipping-lane hot-spots (lat, lon) by flag for plausible positions
_FLAG_HOTSPOTS = {
    "Panama": (8.5, -79.5),
    "Liberia": (6.3, -10.8),
    "United States": (29.0, -92.5),       # US Gulf
    "Iran": (27.0, 55.0),                 # Strait of Hormuz
    "Russia": (44.0, 37.0),               # Novorossiysk
    "Marshall Islands": (9.0, 170.0),
    "Malta": (35.9, 14.5),
    "Greece": (37.9, 23.7),
    "Venezuela": (10.5, -66.9),
    "Singapore": (1.3, 103.8),
}


def generate_ais_mock(n_vessels: int = 500, seed: int = 19) -> pd.DataFrame:
    """Return a DataFrame of mocked crude-tanker AIS observations.

    Includes plausible Latitude/Longitude scattered around each flag's
    shipping-lane hotspot so the data can be plotted on a 3D globe.
    """
    rng = np.random.default_rng(seed)

    flags = np.array(list(_FLAG_WEIGHTS.keys()))
    weights = np.array(list(_FLAG_WEIGHTS.values()))
    weights = weights / weights.sum()

    flag_state = rng.choice(flags, size=n_vessels, p=weights)
    destination = rng.choice(_DESTINATIONS, size=n_vessels)

    # Realistic VLCC / Suezmax / Aframax mix: 0.7M–2.2M bbls
    cargo = rng.normal(loc=1_400_000, scale=400_000, size=n_vessels)
    cargo = np.clip(cargo, 250_000, 2_250_000).astype(int)

    # MMSI numbers are 9 digits
    mmsi = rng.integers(low=200_000_000, high=775_000_000, size=n_vessels)

    prefixes = rng.choice(_VESSEL_PREFIXES, size=n_vessels)
    suffixes = rng.choice(_VESSEL_SUFFIXES, size=n_vessels)
    numbers = rng.integers(1, 99, size=n_vessels)
    vessel_names = [f"{p} {s} {n}" for p, s, n in zip(prefixes, suffixes, numbers)]

    lats = np.empty(n_vessels, dtype=float)
    lons = np.empty(n_vessels, dtype=float)
    for i, f in enumerate(flag_state):
        lat0, lon0 = _FLAG_HOTSPOTS.get(str(f), (0.0, 0.0))
        lats[i] = np.clip(lat0 + rng.normal(0, 8.0), -85.0, 85.0)
        lons[i] = ((lon0 + rng.normal(0, 15.0) + 180.0) % 360.0) - 180.0

    df = pd.DataFrame(
        {
            "Vessel_Name": vessel_names,
            "MMSI": mmsi,
            "Cargo_Volume_bbls": cargo,
            "Destination": destination,
            "Flag_State": flag_state,
            "Latitude": lats,
            "Longitude": lons,
        }
    )
    return df


# ---------------------------------------------------------------------------
# 4. Live AIS (stubbed — key-gated)
# ---------------------------------------------------------------------------
def fetch_live_ais(api_key: str | None = None) -> pd.DataFrame:
    """Live AIS via aisstream.io — currently a documented stub.

    aisstream.io is free but requires a GitHub-linked API key (issued at
    https://aisstream.io/apikeys). Their protocol is a JSON subscription
    over ``wss://stream.aisstream.io/v0/stream`` with an ``APIKey`` field
    and geographic bounding boxes. Hooking this up means:

      1. Add ``websockets`` to ``requirements.txt``.
      2. Accept ``api_key`` from ``AISSTREAM_API_KEY`` env var.
      3. Open a background asyncio task that consumes for ~20s, filters
         message type 1/2/3/5 for cargo-type ``80`` (crude tanker),
         normalises into the same schema as :func:`generate_ais_mock`.

    Until an API key is provided we raise a clear ``NotImplementedError`` so
    the caller (``app.py``) can gracefully fall back to the mock generator.
    """
    raise NotImplementedError(
        "Live AIS disabled: set AISSTREAM_API_KEY to enable (aisstream.io "
        "requires a free GitHub-linked key)."
    )


__all__ = [
    "fetch_pricing_data",
    "simulate_inventory",
    "generate_ais_mock",
    "fetch_live_ais",
]
