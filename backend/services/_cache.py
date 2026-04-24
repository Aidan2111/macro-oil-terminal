"""Tiny TTL cache helper for the router layer.

One cache key per endpoint is enough — the routes take no query params.
A FastAPI dependency wraps the underlying service callable and caches
the Pydantic-validated response for ``ttl_seconds``. Exceptions are
never cached.

Kept dependency-free (no aiocache, no redis) because App Service scales
to a single process per instance; TTLs are short enough that cross-
instance staleness is a non-issue.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    expires_at: float
    value: T


class TTLCache(Generic[T]):
    """Single-slot TTL cache. Thread-safe. Exceptions bypass the cache."""

    def __init__(self, ttl_seconds: float):
        self.ttl_seconds = float(ttl_seconds)
        self._entry: _Entry[T] | None = None
        self._lock = Lock()

    def get_or_compute(self, factory: Callable[[], T]) -> T:
        now = time.monotonic()
        with self._lock:
            entry = self._entry
            if entry is not None and entry.expires_at > now:
                return entry.value
        value = factory()
        with self._lock:
            self._entry = _Entry(expires_at=time.monotonic() + self.ttl_seconds, value=value)
        return value

    def invalidate(self) -> None:
        with self._lock:
            self._entry = None
