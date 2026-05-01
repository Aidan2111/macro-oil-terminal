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


class CorroborationSnapshot(BaseModel):
    """Cross-source price-corroboration snapshot (issue #97).

    yfinance is the primary source for Brent/WTI; FRED's daily
    DCOILBRENTEU + DCOILWTICO series are the secondary check. A
    `max_relative_delta` > 2% flips `/api/data-quality` for the
    yfinance row to amber.
    """

    yfinance: dict[str, float | None] = Field(
        default_factory=dict,
        description="Primary {brent, wti} closes (USD/bbl). May contain None.",
    )
    fred: dict[str, float | None] = Field(
        default_factory=dict,
        description="FRED {brent, wti} closes (USD/bbl). None on fetch failure.",
    )
    max_relative_delta: float | None = Field(
        default=None,
        description="max(|yf - fred| / fred) across both legs; None if FRED unavailable.",
    )


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
    corroboration: CorroborationSnapshot | None = Field(
        default=None,
        description="Cross-source price corroboration vs FRED (issue #97).",
    )
