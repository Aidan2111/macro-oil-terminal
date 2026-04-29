"""OFAC sanctions wrapper service (issue #81).

Thin shim around ``providers.ofac.compute_delta`` that adds the
standard data-quality instrumentation. Counted as one provider in
``/api/data-quality`` so it ages amber if the daily fetch fails.
"""

from __future__ import annotations

import logging
import threading
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


_DQ_LAST_FETCH: dict[str, object] = {
    "last_good_at": None,
    "n_obs": None,
    "latency_ms": None,
    "message": None,
    "status": "amber",
}
_DQ_STATE_LOCK = threading.Lock()


def get_last_fetch_state() -> dict[str, object]:
    with _DQ_STATE_LOCK:
        return dict(_DQ_LAST_FETCH)


def record_fetch_success(*, n_obs: Optional[int], latency_ms: Optional[int] = None) -> None:
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH.update(
            {
                "last_good_at": datetime.now(timezone.utc),
                "n_obs": n_obs,
                "latency_ms": latency_ms,
                "message": None,
                "status": "green",
            }
        )


def record_fetch_failure(message: str) -> None:
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH.update({"message": message, "status": "red"})


def compute_envelope() -> dict[str, Any]:
    from providers import ofac

    t0 = _time.monotonic()
    try:
        payload = ofac.compute_delta()
    except Exception as exc:
        record_fetch_failure(f"OFAC fetch failed: {type(exc).__name__}: {exc}")
        raise
    latency_ms = int((_time.monotonic() - t0) * 1000.0)
    n_obs = sum(int(v) for v in payload.get("totals", {}).values())
    record_fetch_success(n_obs=n_obs, latency_ms=latency_ms)
    return payload
