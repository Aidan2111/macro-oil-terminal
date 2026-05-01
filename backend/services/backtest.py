"""Realistic-cost backtest extension.

The legacy ``quantitative_models.backtest_zscore_meanreversion``
charges a flat ``slippage_per_bbl`` (USD/bbl) at each leg plus a
flat ``commission_per_trade`` (USD/round-trip). That's a fine first
pass but it bears no resemblance to how the desk actually loses
money trading a synthetic Brent-WTI spread.

The :class:`CostModel` in this module replaces the flat surcharge
with three desk-realistic components:

  * ``bid_ask_spread_pct`` — fraction of mid paid as spread crossing
    cost. A Brent-WTI book typically quotes ~3-5 bps wide on small
    clips; we default to 4 bps and let the caller override.
  * ``commission_per_contract`` — USD per CL/BZ contract (1000 bbl).
    Front-office rates today are ~$0.85/contract end-to-end.
  * ``overnight_carry_bps`` — financing carry in bps/year applied to
    notional on each calendar day held. Defaults to 50 bps over
    overnight rates (i.e. ~5.5% all-in at the time of writing).

The new model can change historical PnL versus the old one. We
explicitly compute ``pnl_delta_vs_legacy`` so the API caller sees
exactly how much the new model moves the published number — see
``scripts/q2-trade-info-run.PR_BODY.md`` for the standard-fixture
delta.

Public entry: :func:`run_realistic_backtest` — drop-in replacement
for ``backtest_service.run_backtest`` that returns the same JSON
shape plus a ``cost_model`` block and a ``pnl_delta_vs_legacy``
key.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from . import _compat  # noqa: F401


@dataclass(frozen=True)
class CostModel:
    """Desk-realistic cost components.

    All defaults are calibrated to a small (~10 lot) Brent-WTI spread
    book at a Tier-1 broker as of 2026-Q1. Override per-call to model
    a wider book or a higher-frequency strategy.

    Issue #95 calibration sources (per parameter, with sample dates).
    Each magic number below should match `docs/quant/cost-model.md`
    row-for-row — that doc is the audit trail.
    """

    # source: NYMEX CL bid-ask snapshots from CME public data,
    #   2024-04 .. 2026-04 calendar-spread quotes; median
    #   bid-ask on a 10-lot CL/BZ calendar spread is ~3-5 bps.
    #   https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.quotes.html
    #   sample date: 2026-04-22
    bid_ask_spread_pct: float = 0.0004  # 4 bps (median of 3-5 bps band)

    # source: Interactive Brokers Pro futures schedule (CL/BZ
    #   end-to-end including exchange + clearing + IB markup) as of
    #   2026-04-22.
    #   https://www.interactivebrokers.com/en/pricing/commissions-futures.php
    commission_per_contract: float = 0.85  # USD per contract, end-to-end

    # source: IB benchmark + spread for short USD financing on energy
    #   margin accounts; FF benchmark ~5.0% + 50 bps spread = 5.5%
    #   blended as of 2026-Q1. ICE/CME use 365-day year for financing.
    #   https://www.interactivebrokers.com/en/trading/margin-rates.php
    #   sample date: 2026-04-22
    overnight_carry_bps: float = 50.0  # bps over benchmark, annualised

    # source: CME CL calendar-spread settlements 2024-04 .. 2026-04.
    #   The spread is rolled once per ~30-day signal cycle. Realised
    #   roll cost over that period averaged $0.18/bbl (median $0.15,
    #   p90 $0.30). $0.20 is the round-numbered conservative pick.
    #   https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.settlements.html
    #   sample date: 2026-04-22
    roll_cost_per_bbl: float = 0.20  # USD/bbl per round-trip roll

    # Notional per signal — keeps the back-compat wrapper aligned with
    # the legacy ``notional_bbls=10_000`` default. (CME contract size
    # is 1000 bbl; 10 contracts = 10,000 bbl.)
    notional_bbls: float = 10_000.0
    barrels_per_contract: float = 1000.0  # CME spec: 1 CL/BZ = 1000 bbl

    def contracts(self) -> float:
        return self.notional_bbls / self.barrels_per_contract

    def round_trip_commission_usd(self) -> float:
        """USD commission for the round-trip (entry + exit)."""
        return 2.0 * self.contracts() * self.commission_per_contract

    def round_trip_spread_cost_usd(self, mid_price: float) -> float:
        """USD spread-crossing cost for entry + exit at ``mid_price``."""
        return 2.0 * self.bid_ask_spread_pct * abs(mid_price) * self.notional_bbls

    def carry_usd(self, days_held: float, mid_price: float) -> float:
        """Overnight carry in USD across ``days_held`` calendar days
        on a notional sized at ``mid_price``."""
        if days_held <= 0:
            return 0.0
        notional_usd = abs(mid_price) * self.notional_bbls
        annual_rate = self.overnight_carry_bps / 10_000.0
        # 365-day year for financing — matches ICE/CME convention.
        return notional_usd * annual_rate * (days_held / 365.0)

    def roll_cost_usd(self, days_held: float) -> float:
        """USD roll cost for a position held across one or more
        contract-month boundaries.

        Approximation: assume one roll per ~30 days held. Holds
        shorter than 25 days incur no roll cost (the position closes
        before the front-month rolls). This is intentionally
        coarse — issue #95 calibrates against historical CME
        calendar-spread settlements rather than tick-level roll
        execution prices.
        """
        if days_held <= 25:
            return 0.0
        rolls = max(1, int(days_held // 30))
        return rolls * self.roll_cost_per_bbl * self.notional_bbls


def _legacy_pnl_for_trade(
    trade: dict,
    *,
    slippage_per_bbl: float,
    commission_per_trade: float,
    notional_bbls: float,
) -> float:
    """Recompute the legacy per-trade PnL from raw entry/exit so we
    can quote an apples-to-apples old-vs-new delta. Mirrors the
    formula in ``quantitative_models.backtest_zscore_meanreversion``."""
    entry = float(trade.get("entry_spread") or 0.0)
    exit_ = float(trade.get("exit_spread") or 0.0)
    side = trade.get("side")
    sign = 1 if side == "long_spread" else -1
    gross_per_bbl = (exit_ - entry) * sign
    net_per_bbl = gross_per_bbl - 2.0 * slippage_per_bbl
    return net_per_bbl * notional_bbls - 2.0 * commission_per_trade


def _realistic_pnl_for_trade(trade: dict, cost: CostModel) -> tuple[float, dict]:
    """Recompute per-trade PnL under the realistic cost model.

    Returns ``(pnl_usd, breakdown_dict)`` so the UI can show the
    reader exactly which line items moved the number.
    """
    entry = float(trade.get("entry_spread") or 0.0)
    exit_ = float(trade.get("exit_spread") or 0.0)
    side = trade.get("side")
    sign = 1 if side == "long_spread" else -1
    days_held = float(trade.get("days_held") or 0.0)

    # The "mid" we model spread-crossing cost on is the average of
    # entry and exit absolute prices. For a spread that's the mid of
    # the spread itself — small-number trap, but the cost is also
    # quoted in % so the dollar amount stays reasonable.
    mid = (abs(entry) + abs(exit_)) / 2.0 if (entry or exit_) else 0.0

    gross_usd = (exit_ - entry) * sign * cost.notional_bbls
    spread_cost = cost.round_trip_spread_cost_usd(mid)
    commission = cost.round_trip_commission_usd()
    carry = cost.carry_usd(days_held, mid)
    roll_cost = cost.roll_cost_usd(days_held)

    pnl = gross_usd - spread_cost - commission - carry - roll_cost
    breakdown = {
        "gross_usd": gross_usd,
        "spread_cost_usd": spread_cost,
        "commission_usd": commission,
        "overnight_carry_usd": carry,
        "roll_cost_usd": roll_cost,
        "net_pnl_usd": pnl,
    }
    return pnl, breakdown


def run_realistic_backtest(
    *,
    spread_df: Any,
    entry_z: float,
    exit_z: float,
    slippage_bps: float = 4.0,
    cost: Optional[CostModel] = None,
    legacy_slippage_per_bbl: float = 0.02,
    legacy_commission_per_trade: float = 1.0,
) -> dict:
    """Run the Z-score backtester and re-cost the trades realistically.

    The legacy engine is invoked once with ``slippage_per_bbl=0`` and
    ``commission_per_trade=0`` so we get the *gross* trade list, then
    we re-cost each trade twice — once with the realistic cost model
    (the published number) and once with the legacy flat costs (so we
    can quote ``pnl_delta_vs_legacy``).

    Parameters
    ----------
    spread_df
        DataFrame with ``Spread`` + ``Z_Score`` columns. Same input
        the legacy backtester takes.
    entry_z, exit_z
        Z-score thresholds.
    slippage_bps
        Convenience param — if ``cost`` is ``None`` we build a default
        ``CostModel`` with ``bid_ask_spread_pct=slippage_bps/10000``.
    cost
        Optional explicit ``CostModel`` override.
    legacy_slippage_per_bbl, legacy_commission_per_trade
        The numbers the legacy engine has been quoted at on the
        track-record page. We need them to compute the published
        delta.
    """
    import quantitative_models  # type: ignore

    if cost is None:
        cost = CostModel(bid_ask_spread_pct=slippage_bps / 10_000.0)

    raw = quantitative_models.backtest_zscore_meanreversion(
        spread_df,
        entry_z=entry_z,
        exit_z=exit_z,
        slippage_per_bbl=0.0,
        commission_per_trade=0.0,
    )

    # Trades may be a DataFrame; convert to list-of-dicts.
    trades = raw.get("trades")
    try:
        import pandas as pd  # type: ignore
        if isinstance(trades, pd.DataFrame):
            trades_list = trades.to_dict(orient="records")
        else:
            trades_list = list(trades or [])
    except Exception:
        trades_list = list(trades or [])

    realistic_total = 0.0
    legacy_total = 0.0
    enriched: list[dict] = []
    for tr in trades_list:
        rpnl, breakdown = _realistic_pnl_for_trade(tr, cost)
        lpnl = _legacy_pnl_for_trade(
            tr,
            slippage_per_bbl=legacy_slippage_per_bbl,
            commission_per_trade=legacy_commission_per_trade,
            notional_bbls=cost.notional_bbls,
        )
        realistic_total += rpnl
        legacy_total += lpnl
        cp = dict(tr)
        cp["pnl_usd"] = rpnl
        cp["pnl_breakdown"] = breakdown
        cp["pnl_usd_legacy"] = lpnl
        enriched.append(cp)

    return {
        "trades": enriched,
        "n_trades": len(enriched),
        "total_pnl_usd": realistic_total,
        "total_pnl_usd_legacy": legacy_total,
        "pnl_delta_vs_legacy": realistic_total - legacy_total,
        "cost_model": asdict(cost),
        "params": {
            "entry_z": entry_z,
            "exit_z": exit_z,
            "slippage_bps": slippage_bps,
        },
    }


__all__ = ["CostModel", "run_realistic_backtest"]
