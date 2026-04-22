"""AIS orchestrator (thin shim over the aisstream.io provider + historical snapshot)."""

from __future__ import annotations

import os


def active_ais_provider() -> str:
    if os.environ.get("AISSTREAM_API_KEY"):
        return "aisstream.io (live websocket)"
    return "Historical snapshot (Q3 2024, labeled placeholder)"


def fetch_ais(n_vessels: int = 500):
    # Delegate to data_ingestion.fetch_ais_data to preserve a single code path
    from data_ingestion import fetch_ais_data
    return fetch_ais_data(n_vessels=n_vessels)
