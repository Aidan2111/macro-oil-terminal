"""Issue #95 — pin every cost-model parameter to a hand-calculated PnL.

Each parameter in :class:`CostModel` carries a citable source comment
(see ``docs/quant/cost-model.md``). This test fixes those parameters
to their default values and asserts the PnL on a one-trade fixture
matches the hand calculation to within ±5%. Any future change to the
cost defaults that drifts more than 5% from the documented number
will fail this test — protecting the audit trail.
"""

from __future__ import annotations

import sys
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.backtest import CostModel, _realistic_pnl_for_trade


# ---------------------------------------------------------------------------
# Hand-calculated reference for one short-spread trade.
# ---------------------------------------------------------------------------
# Inputs:
#   * Side: short_spread (sign = -1)
#   * entry_spread: 6.50 USD/bbl
#   * exit_spread:  4.00 USD/bbl  (short captures 2.50 USD/bbl)
#   * days_held: 30 calendar days (one roll triggers)
#   * notional_bbls: 10_000 (10 CL/BZ contracts)
#
# CostModel defaults (issue #95 calibration, dated 2026-04-22):
#   * bid_ask_spread_pct = 0.0004
#   * commission_per_contract = 0.85
#   * overnight_carry_bps = 50.0
#   * roll_cost_per_bbl = 0.20
#
# Hand calculation:
#   gross_usd        = (4.00 - 6.50) * -1 * 10_000 =  $25,000.00
#   mid_price        = (6.50 + 4.00) / 2          =       $5.25
#   spread_cost_usd  = 2 * 0.0004 * 5.25 * 10_000 =      $42.00
#   commission_usd   = 2 * 10 * 0.85              =      $17.00
#   carry_usd        = 5.25 * 10_000 * (50/10000) * (30/365) ≈ $21.575...
#                      = $21.57534246575...
#   roll_cost_usd    = 1 roll * $0.20 * 10_000    =   $2,000.00
#   net_pnl_usd      = 25_000 - 42 - 17 - 21.575 - 2_000 = $22,919.42(...)
# ---------------------------------------------------------------------------
EXPECTED_PNL_USD = 22_919.42
TOLERANCE_PCT = 0.05  # 5%


def test_one_trade_pnl_matches_hand_calculation():
    """A 30-day short-spread trade with default costs PnLs to ~$22,919."""
    cost = CostModel()  # defaults are the documented Q2-2026 numbers

    trade = {
        "side": "short_spread",
        "entry_spread": 6.50,
        "exit_spread": 4.00,
        "days_held": 30,
    }
    pnl, breakdown = _realistic_pnl_for_trade(trade, cost)

    assert pnl == pytest.approx(EXPECTED_PNL_USD, rel=TOLERANCE_PCT), (
        f"Net PnL drifted from the documented hand calc. "
        f"Got {pnl:.2f}, expected {EXPECTED_PNL_USD:.2f} ± {TOLERANCE_PCT*100:.0f}%. "
        f"Breakdown: {breakdown}. "
        f"Either the cost defaults moved without updating "
        f"`docs/quant/cost-model.md`, or the calculation in "
        f"_realistic_pnl_for_trade has changed. Reconcile both."
    )


def test_breakdown_lines_match_hand_calculation():
    """Each individual cost line must agree with the audit doc."""
    cost = CostModel()
    trade = {
        "side": "short_spread",
        "entry_spread": 6.50,
        "exit_spread": 4.00,
        "days_held": 30,
    }
    _, breakdown = _realistic_pnl_for_trade(trade, cost)

    assert breakdown["gross_usd"] == pytest.approx(25_000.00, rel=1e-6)
    assert breakdown["spread_cost_usd"] == pytest.approx(42.00, rel=1e-3)
    assert breakdown["commission_usd"] == pytest.approx(17.00, rel=1e-6)
    # Carry: 5.25 * 10_000 * 0.005 * (30 / 365) = 21.5753...
    assert breakdown["overnight_carry_usd"] == pytest.approx(21.5753, rel=1e-3)
    # Roll cost: 1 roll * $0.20/bbl * 10_000 bbl = $2_000
    assert breakdown["roll_cost_usd"] == pytest.approx(2_000.00, rel=1e-6)


def test_roll_cost_is_zero_for_short_holds():
    """Holds <= 25 days incur no roll cost — position closes before
    the front month rolls."""
    cost = CostModel()
    trade = {
        "side": "long_spread",
        "entry_spread": 4.0,
        "exit_spread": 5.0,
        "days_held": 12,  # well under the 25-day cutoff
    }
    _, breakdown = _realistic_pnl_for_trade(trade, cost)
    assert breakdown["roll_cost_usd"] == 0.0


def test_roll_cost_scales_with_days_held():
    """A 90-day hold incurs three rolls (one per ~30 days)."""
    cost = CostModel()
    trade = {
        "side": "long_spread",
        "entry_spread": 4.0,
        "exit_spread": 5.0,
        "days_held": 90,
    }
    _, breakdown = _realistic_pnl_for_trade(trade, cost)
    # 3 rolls * $0.20/bbl * 10_000 bbl = $6_000
    assert breakdown["roll_cost_usd"] == pytest.approx(6_000.00)
