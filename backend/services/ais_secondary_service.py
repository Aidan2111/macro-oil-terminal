"""Secondary AIS provider shim (issue #107).

Records last-fetch state for the data-quality envelope. When
``AIS_SECONDARY_ENABLED=1`` the operator's secondary-feed integration
calls ``record_fetch_success`` / ``record_fetch_failure`` from
wherever the actual messages land (websocket consumer, REST polling
loop, etc.).

When the secondary is disabled (default) the shim reports status
``amber`` with ``last_good_at=None`` so the data-quality tile shows
"not provisioned" rather than misleadingly green or red.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from . import ais_merger


_LOCK = threading.Lock()
_STATE: dict[str, object] = {
    "last_good_at": None,
    "n_obs": None,
    "latency_ms": None,
    "message": None,
    "status": "amber",
}


def record_fetch_success(*, n_obs: int | None, latency_ms: int | None,
                          message: str | None = None,
                          degraded: bool = False) -> None:
    """Mark a successful poll/message from the secondary AIS feed."""
    with _LOCK:
        _STATE["last_good_at"] = datetime.now(timezone.utc)
        _STATE["n_obs"] = n_obs
        _STATE["latency_ms"] = latency_ms
        _STATE["message"] = message
        _STATE["status"] = "amber" if degraded else "green"


def record_fetch_failure(message: str) -> None:
    with _LOCK:
        _STATE["status"] = "red"
        _STATE["message"] = message


def get_last_fetch_state() -> dict[str, object]:
    """Return a snapshot dict (caller-owned copy)."""
    with _LOCK:
        snap = dict(_STATE)
    if not ais_merger.is_secondary_enabled():
        # Override status when the secondary is intentionally disabled
        # — we don't want a red tile for an unconfigured optional
        # feature.
        return {
            "last_good_at": None,
            "n_obs": None,
            "latency_ms": None,
            "message": "secondary AIS disabled (set AIS_SECONDARY_ENABLED=1)",
            "status": "amber",
        }
    return snap


__all__ = ["record_fetch_success", "record_fetch_failure", "get_last_fetch_state"]
