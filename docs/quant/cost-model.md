# Backtest cost model — calibration audit (issue #95)

The realistic-cost backtest in `backend/services/backtest.py` charges
four desk-realistic components on top of the gross spread move:
bid-ask, commission, overnight carry, and front-month roll cost.
Each parameter must trace back to a citable source — this document is
that audit trail.

## Parameter table

| Parameter | Default | Unit | Source | Sample date |
|---|---|---|---|---|
| `bid_ask_spread_pct` | `0.0004` | fraction of mid | NYMEX CL bid-ask snapshots from CME public data; median bid-ask on a 10-lot CL/BZ calendar spread is 3-5 bps. <https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.quotes.html> | 2026-04-22 |
| `commission_per_contract` | `0.85` | USD per contract | Interactive Brokers Pro futures schedule (CL/BZ end-to-end including exchange + clearing + IB markup). <https://www.interactivebrokers.com/en/pricing/commissions-futures.php> | 2026-04-22 |
| `overnight_carry_bps` | `50.0` | bps over benchmark, annualised | IB benchmark + spread for short USD financing on energy margin accounts (FF benchmark ~5.0% + 50 bps spread = 5.5% blended). <https://www.interactivebrokers.com/en/trading/margin-rates.php> | 2026-Q1 |
| `roll_cost_per_bbl` | `0.20` | USD/bbl per round-trip roll | CME CL calendar-spread settlements 2024-04 .. 2026-04. Realised roll cost averaged $0.18/bbl (median $0.15, p90 $0.30); $0.20 is the round-numbered conservative pick. <https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.settlements.html> | 2026-04-22 |
| `notional_bbls` | `10_000.0` | bbl | Default trade size — 10 CL/BZ contracts at 1000 bbl each. CME spec. | n/a |
| `barrels_per_contract` | `1000.0` | bbl | CME contract spec for both CL and BZ. <https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude_contract_specifications.html> | n/a |

## Hand-calculated reference

`tests/unit/test_backtest_cost_pinning.py` pins a one-trade fixture
to a hand-calculated PnL. Any drift from the documented number that
exceeds ±5% will fail CI — protecting this audit trail.

The reference trade:

- Side: short_spread (entry at $6.50, exit at $4.00 — captures $2.50/bbl)
- 30 days held (one front-month roll triggers)
- 10,000 bbl notional

Hand calc:

```
gross_usd        = (4.00 - 6.50) * -1 * 10_000 = $25,000.00
mid_price        = (6.50 + 4.00) / 2           =      $5.25
spread_cost_usd  = 2 * 0.0004 * 5.25 * 10_000  =     $42.00
commission_usd   = 2 * 10 * 0.85               =     $17.00
carry_usd        = 5.25 * 10_000 * 0.005 * (30 / 365) ≈ $21.58
roll_cost_usd    = 1 roll * $0.20/bbl * 10_000 =  $2,000.00
                                                ------------
net_pnl_usd      ≈ $22,919.42
```

## What this changes vs the legacy cost model

Legacy `quantitative_models.backtest_zscore_meanreversion`:

- Flat `slippage_per_bbl` (default $0.02/bbl) charged at each leg.
- Flat `commission_per_trade` (default $1.00 round-trip).
- No financing or roll cost.

Realistic model:

- bid-ask scales with mid price and notional.
- Commission scales with contract count.
- Carry scales with mid × notional × days held.
- Roll cost scales with notional × number of contract rolls held
  through.

`/api/backtest` exposes `pnl_delta_vs_legacy` so the reader can see
exactly how much the realistic model moves the published number on
the same trade list.

## Calibration cadence

Re-run the audit at least quarterly, or whenever any of:

- IB or CME publishes a fee schedule change.
- The CL term-structure flips regime (contango ↔ backwardation) — roll
  cost can move 2-3× across the regime boundary.
- A new broker is onboarded (e.g. issue #105 / #106 add a Databento
  feed and possibly a different execution venue).

Update the table above with the new sample date and adjust the
`CostModel` defaults in lockstep. The pinning test will fail until the
hand calculation in this doc is updated to match.
