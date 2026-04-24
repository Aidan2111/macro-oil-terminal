"""Inventory response schema.

Shapes the output of ``providers.inventory.fetch_inventory`` +
``quantitative_models.forecast_depletion`` into a JSON payload with
current stocks, 2y history, and a simple linear-regression depletion
forecast.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InventoryPoint(BaseModel):
    """One weekly observation."""

    date: str = Field(..., description="ISO-8601 date of the EIA release")
    commercial_bbls: float | None = Field(
        default=None, description="U.S. commercial crude stocks (bbls)"
    )
    spr_bbls: float | None = Field(
        default=None, description="Strategic Petroleum Reserve stocks (bbls)"
    )
    cushing_bbls: float | None = Field(
        default=None, description="Cushing, OK hub stocks (bbls)"
    )
    total_bbls: float | None = Field(
        default=None, description="Commercial + SPR (bbls)"
    )


class DepletionForecast(BaseModel):
    """Linear-regression forecast from ``forecast_depletion``."""

    daily_depletion_bbls: float = Field(
        ..., description="Slope in bbls/day (negative = drawdown)"
    )
    weekly_depletion_bbls: float = Field(
        ..., description="Slope * 7 (bbls/week)"
    )
    projected_floor_date: str | None = Field(
        default=None,
        description="ISO-8601 date when total breaches floor_bbls, or null",
    )
    r_squared: float = Field(
        ..., description="R^2 of the linear fit on the trailing window"
    )
    floor_bbls: float = Field(..., description="Configured floor threshold (bbls)")


class InventoryResponse(BaseModel):
    """Current stocks + 2y history + depletion forecast."""

    commercial_bbls: float = Field(..., description="Latest commercial (bbls)")
    spr_bbls: float = Field(..., description="Latest SPR (bbls)")
    cushing_bbls: float = Field(..., description="Latest Cushing (bbls)")
    total_bbls: float = Field(..., description="Latest commercial + SPR (bbls)")
    as_of: str = Field(..., description="ISO-8601 date of the latest release")
    source: str = Field(..., description="Upstream provider tag (e.g. 'EIA')")
    history: list[InventoryPoint] = Field(
        default_factory=list,
        description="Trailing 2y of weekly observations (ascending).",
    )
    forecast: DepletionForecast = Field(..., description="Linear depletion fit")
