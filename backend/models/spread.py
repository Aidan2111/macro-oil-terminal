"""Spread schema — stub.

Phase 2 replaces with `SpreadPoint` + `SpreadSeries`.
"""

from __future__ import annotations

from pydantic import BaseModel


class SpreadStub(BaseModel):
    """Placeholder spread schema."""

    status: str
    series: list[dict]
