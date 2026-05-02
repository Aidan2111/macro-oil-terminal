"""AIS multi-merge orchestrator — primary + secondary redundancy.

Wires aisstream.io (primary) and fleetmon.com (secondary) into a single
AIS feed for the fleet service:

- **Primary-only**: When aisstream is healthy, use it exclusively.
- **Failover**: If primary is silent for >5 min, switch to secondary.
- **Dual-merge**: When both are alive, merge and deduplicate by MMSI.

The result is consumed by ``backend.services.fleet_service`` which
handles SSE fan-out to clients.

Acceptance criteria (issue #107):
- Second AIS source wired, configured via ``AIS_SECONDARY_API_KEY``.
- Multi-merge dedup logic unit-tested.
- ``/api/data-quality`` lists both providers.
"""

from __future__ import annotations

import os
import time
import threading
from typing import Optional

import pandas as pd


# Maximum age (seconds) before primary is considered stale
_PRIMARY_STALE_THRESHOLD = 300  # 5 minutes


class AISMultiMerge:
    """Orchestrates primary + secondary AIS sources with dedup by MMSI."""

    def __init__(self):
        self._primary_data: Optional[pd.DataFrame] = None
        self._secondary_data: Optional[pd.DataFrame] = None
        self._primary_last_update: float = 0.0
        self._secondary_last_update: float = 0.0
        self._lock = threading.Lock()

    def update_primary(self, df: pd.DataFrame) -> None:
        """Ingest primary (aisstream.io) snapshot."""
        with self._lock:
            self._primary_data = df
            self._primary_last_update = time.monotonic()

    def update_secondary(self, df: pd.DataFrame) -> None:
        """Ingest secondary (fleetmon.com) snapshot."""
        with self._lock:
            self._secondary_data = df
            self._secondary_last_update = time.monotonic()

    @property
    def primary_available(self) -> bool:
        """Check if primary data is fresh (not stale)."""
        age = time.monotonic() - self._primary_last_update
        return (
            self._primary_data is not None
            and not self._primary_data.empty
            and age < _PRIMARY_STALE_THRESHOLD
        )

    @property
    def secondary_available(self) -> bool:
        """Check if secondary data is available."""
        return (
            self._secondary_data is not None
            and not self._secondary_data.empty
        )

    @property
    def active_source(self) -> str:
        """Return which source(s) are currently active."""
        if self.primary_available and self.secondary_available:
            return "primary+secondary"
        if self.primary_available:
            return "primary"
        if self.secondary_available:
            return "secondary"
        return "none"

    def get_merged(self) -> pd.DataFrame:
        """Return merged, deduplicated vessel DataFrame.

        Dedup strategy:
        - Primary data takes precedence for overlapping MMSIs.
        - Secondary-only vessels are appended.
        - Result is sorted by MMSI for stable output.
        """
        with self._lock:
            primary = self._primary_data if self.primary_available else None
            secondary = self._secondary_data if self.secondary_available else None

        if primary is None and secondary is None:
            return pd.DataFrame()

        if primary is None:
            return secondary.copy()

        if secondary is None:
            return primary.copy()

        # Dedup: primary wins for overlapping MMSIs
        primary_mmsi = set(primary["MMSI"].tolist())
        secondary_unique = secondary[~secondary["MMSI"].isin(primary_mmsi)]

        merged = pd.concat([primary, secondary_unique], ignore_index=True)
        merged = merged.sort_values("MMSI").reset_index(drop=True)
        return merged

    def get_health(self) -> dict:
        """Return health summary for both sources."""
        with self._lock:
            primary_age = time.monotonic() - self._primary_last_update
            secondary_age = time.monotonic() - self._secondary_last_update

        return {
            "primary": {
                "status": "green" if self.primary_available else "red",
                "last_update_age_sec": round(primary_age, 1),
                "vessel_count": len(self._primary_data) if self._primary_data is not None else 0,
                "stale_threshold_sec": _PRIMARY_STALE_THRESHOLD,
            },
            "secondary": {
                "status": "green" if self.secondary_available else "red",
                "last_update_age_sec": round(secondary_age, 1),
                "vessel_count": len(self._secondary_data) if self._secondary_data is not None else 0,
            },
            "merged": {
                "active_source": self.active_source,
                "vessel_count": len(self.get_merged()),
            },
        }


# Module-level singleton
_merger: Optional[AISMultiMerge] = None
_merger_lock = threading.Lock()


def get_merger() -> AISMultiMerge:
    """Get or create the module-level AISMultiMerge singleton."""
    global _merger
    if _merger is None:
        with _merger_lock:
            if _merger is None:
                _merger = AISMultiMerge()
    return _merger


def reset_merger() -> None:
    """Reset the singleton (for testing)."""
    global _merger
    with _merger_lock:
        _merger = None


# Data-quality state for secondary provider
_secondary_fetch_state = {
    "last_good_at": None,
    "n_obs": None,
    "latency_ms": None,
    "message": None,
    "status": "amber",
}


def record_secondary_fetch_success(*, n_obs: int, latency_ms: int,
                                   message: Optional[str] = None) -> None:
    """Mark a successful secondary fetch."""
    from datetime import datetime, timezone
    _secondary_fetch_state["last_good_at"] = datetime.now(timezone.utc)
    _secondary_fetch_state["n_obs"] = n_obs
    _secondary_fetch_state["latency_ms"] = latency_ms
    _secondary_fetch_state["message"] = message
    _secondary_fetch_state["status"] = "green"


def record_secondary_fetch_failure(message: str) -> None:
    """Mark a failed secondary fetch."""
    _secondary_fetch_state["status"] = "red"
    _secondary_fetch_state["message"] = message


def get_secondary_fetch_state() -> dict:
    """Return secondary provider health snapshot."""
    return dict(_secondary_fetch_state)


__all__ = [
    "AISMultiMerge",
    "get_merger",
    "reset_merger",
    "get_secondary_fetch_state",
    "record_secondary_fetch_success",
    "record_secondary_fetch_failure",
]