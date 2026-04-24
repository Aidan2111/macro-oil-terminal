"""Spread response schema.

Wraps the Brent-WTI daily output of ``compute_spread_zscore`` into a
JSON-safe shape. The ``history`` list is last-90-bars, each row an
ISO-date + float fields so the frontend can render a sparkline with
no further reshape.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SpreadPoint(BaseModel):
    """One daily bar of the Brent-WTI spread series."""

    date: str = Field(..., description="ISO-8601 date (YYYY-MM-DD)")
    brent: float | None = Field(default=None, description="Brent close (USD/bbl)")
    wti: float | None = Field(default=None, description="WTI close (USD/bbl)")
    spread: float | None = Field(default=None, description="Brent - WTI (USD/bbl)")
    z_score: float | None = Field(default=None, description="Rolling 90d Z-score")


class SpreadResponse(BaseModel):
    """Current Brent-WTI prices + latest spread stretch + 90-day history."""

    brent: float = Field(..., description="Latest Brent close (USD/bbl)")
    wti: float = Field(..., description="Latest WTI close (USD/bbl)")
    spread: float = Field(..., description="Latest Brent - WTI (USD/bbl)")
    stretch: float | None = Field(
        default=None,
        description="Latest rolling 90d Z-score of the spread (signed)",
    )
    stretch_band: str = Field(
        ...,
        description=(
            "Qualitative label for |stretch|: "
            "Calm / Normal / Stretched / Very Stretched / Extreme"
        ),
    )
    as_of: str = Field(..., description="ISO-8601 date of the latest bar")
    source: str = Field(..., description="Upstream provider tag (e.g. 'yfinance')")
    history: list[SpreadPoint] = Field(
        default_factory=list,
        description="Last 90 daily bars (ascending).",
    )
