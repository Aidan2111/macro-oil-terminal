"""Inventory provider orchestrator.

Priority chain:
  1. EIA dnav LeafHandler — real, keyless, official EIA data.
  2. FRED API — requires FRED_API_KEY.

There is intentionally **no simulator fallback** in the production path.
If every provider fails, we raise :class:`InventoryUnavailable` and let
the UI surface a clear error state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd


class InventoryUnavailable(RuntimeError):
    """Raised when no inventory provider could return a frame."""


@dataclass
class InventoryResult:
    frame: pd.DataFrame
    source: str           # short provider name: "EIA" / "FRED"
    source_url: str       # best-effort canonical link for citation
    fetched_at: pd.Timestamp


def _try_eia() -> Tuple[pd.DataFrame, str]:
    from . import _eia
    df = _eia.fetch_inventory()
    return df, "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=pet&s=WCESTUS1&f=W"


def _try_fred() -> Tuple[pd.DataFrame, str]:
    from . import _fred
    df = _fred.fetch_inventory()
    return df, "https://fred.stlouisfed.org/series/WCESTUS1"


def fetch_inventory() -> InventoryResult:
    """Try EIA first, then FRED. Raise ``InventoryUnavailable`` on total failure."""
    errors: list[str] = []
    for name, getter in (("EIA", _try_eia), ("FRED", _try_fred)):
        try:
            df, url = getter()
            if df is None or df.empty:
                errors.append(f"{name}: returned empty frame")
                continue
            return InventoryResult(
                frame=df,
                source=name,
                source_url=url,
                fetched_at=pd.Timestamp.utcnow(),
            )
        except Exception as exc:
            errors.append(f"{name}: {exc!r}")
    raise InventoryUnavailable(
        "No inventory provider returned data. Attempts:\n- " + "\n- ".join(errors)
    )


def active_inventory_provider() -> str:
    """Return the name of the provider that would be tried first."""
    primary = "EIA v2 API (keyed)" if os.environ.get("EIA_API_KEY") else "EIA dnav (keyless)"
    if os.environ.get("FRED_API_KEY"):
        return f"{primary} → FRED (keyed) fallback"
    return primary
