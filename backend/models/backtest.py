"""Backtest request + response schemas.

Small, explicit pydantic v2 models so FastAPI does the shape validation and
the Next.js frontend gets a stable contract. Matches the shape returned by
``services.backtest_service.run_backtest``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    """POST /api/backtest body."""

    entry_z: float = Field(2.0, description="Absolute Z-score that triggers entry.")
    exit_z: float = Field(0.2, description="Absolute Z-score that triggers flat.")
    lookback_days: int = Field(
        365,
        gt=30,
        le=3650,
        description="History window fed into the backtest.",
    )
    slippage_per_bbl: float = Field(
        0.0, ge=0.0, description="Per-barrel slippage applied on each fill."
    )
    commission_per_trade: float = Field(
        0.0, ge=0.0, description="Flat USD commission charged per leg fill."
    )


class EquityPoint(BaseModel):
    """Single point on the cumulative-PnL equity curve."""

    Date: Optional[str] = None
    cum_pnl_usd: Optional[float] = None


class BacktestResponse(BaseModel):
    """POST /api/backtest response."""

    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    calmar: Optional[float] = None
    var_95: Optional[float] = None
    es_95: Optional[float] = None
    max_drawdown: Optional[float] = None
    hit_rate: Optional[float] = None
    total_pnl_usd: Optional[float] = None
    n_trades: int = 0
    avg_days_held: Optional[float] = None
    avg_pnl_per_bbl: Optional[float] = None
    rolling_12m_sharpe: Optional[float] = None
    equity_curve: list[dict] = Field(default_factory=list)
    trades: list[dict] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)


__all__ = ["BacktestRequest", "BacktestResponse", "EquityPoint"]
