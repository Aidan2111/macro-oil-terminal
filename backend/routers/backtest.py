"""POST /api/backtest — synchronous Z-score mean-reversion backtest.

Computes in 2–5 seconds on a year of daily data. No SSE — the frontend
fires a single ``fetch('/api/backtest', {method:'POST', body: ...})`` and
renders the returned equity curve + trades table.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.backtest import BacktestRequest, BacktestResponse
from ..services import backtest_service

router = APIRouter(tags=["backtest"])


@router.post("/backtest", response_model=BacktestResponse)
def run_backtest(body: BacktestRequest) -> BacktestResponse:
    """Run the backtest with the supplied parameters."""
    if body.exit_z >= body.entry_z:
        # Trivially invalid — you'd exit the instant you entered.
        raise HTTPException(
            status_code=422,
            detail="exit_z must be strictly less than entry_z",
        )
    try:
        payload = backtest_service.run_backtest(
            entry_z=body.entry_z,
            exit_z=body.exit_z,
            lookback_days=body.lookback_days,
            slippage_per_bbl=body.slippage_per_bbl,
            commission_per_trade=body.commission_per_trade,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return BacktestResponse(**payload)


__all__ = ["router"]
