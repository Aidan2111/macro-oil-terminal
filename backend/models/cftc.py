"""CFTC Commitments-of-Traders response schema.

Shapes the weekly COT frame from ``providers._cftc.fetch_wti_positioning``
into a JSON payload with current net positions, a 3y managed-money
Z-score, and the full weekly history.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CFTCPoint(BaseModel):
    """One weekly COT observation (Tuesday report date)."""

    date: str = Field(..., description="ISO-8601 report date")
    mm_net: int | None = Field(
        default=None, description="Managed Money net (contracts)"
    )
    producer_net: int | None = Field(
        default=None, description="Producer / Merchant net (contracts)"
    )
    swap_net: int | None = Field(
        default=None, description="Swap Dealer net (contracts)"
    )
    open_interest: int | None = Field(
        default=None, description="Total open interest (contracts)"
    )


class CFTCResponse(BaseModel):
    """Latest COT snapshot + 3y history."""

    mm_net: int = Field(..., description="Latest Managed Money net (contracts)")
    commercial_net: int = Field(
        ...,
        description=(
            "Latest commercial (Producer + Swap) net — the hedger side "
            "of the tape, signed as contracts"
        ),
    )
    mm_zscore_3y: float | None = Field(
        default=None,
        description="Z-score of latest mm_net vs trailing ~156 weeks",
    )
    as_of: str = Field(..., description="ISO-8601 date of the latest report")
    market: str = Field(..., description="CFTC market name (e.g. WTI-PHYSICAL ...)")
    source_url: str = Field(..., description="Upstream CFTC zip URL used")
    history: list[CFTCPoint] = Field(
        default_factory=list,
        description="Weekly history covering ~3y (ascending).",
    )
