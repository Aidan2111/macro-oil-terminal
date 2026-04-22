"""Pluggable data providers for the oil terminal.

Each submodule exposes a single ``fetch(...)`` function that returns a
canonical pandas object (or raises). The orchestrator functions live
here and try providers in priority order, falling through on any
failure so the UI never breaks.

Envs consulted:
  * TWELVEDATA_API_KEY  — unlocks providers._twelvedata (pricing)
  * EIA_API_KEY         — unlocks providers._eia         (inventory)
  * FRED_API_KEY        — unlocks providers._fred        (inventory)
  * AISSTREAM_API_KEY   — unlocks providers._aisstream   (AIS)
"""

from __future__ import annotations

from .pricing import (
    fetch_pricing_daily,
    fetch_pricing_intraday,
    active_pricing_provider,
)
from .inventory import fetch_inventory, active_inventory_provider
from .ais import fetch_ais, active_ais_provider

__all__ = [
    "fetch_pricing_daily",
    "fetch_pricing_intraday",
    "active_pricing_provider",
    "fetch_inventory",
    "active_inventory_provider",
    "fetch_ais",
    "active_ais_provider",
]
