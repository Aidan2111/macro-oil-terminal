"""News headlines wrapper service (issue #80).

Thin shim around `providers.news_rss.fetch_recent` that adds the
standard `data_quality.record_fetch_*` instrumentation.
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
    """Pull recent headlines (cached 15min by the provider). Records DQ state."""
    from providers import news_rss

    t0 = _time.monotonic()
    try:
        payload = news_rss.fetch_recent()
    except Exception as exc:
        record_fetch_failure(f"News fetch failed: {type(exc).__name__}: {exc}")
        raise
    latency_ms = int((_time.monotonic() - t0) * 1000.0)
    record_fetch_success(n_obs=int(payload.get("count", 0)), latency_ms=latency_ms)
    return payload
