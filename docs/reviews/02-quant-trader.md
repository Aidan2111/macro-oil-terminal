# 02 — Quant-Trader Review (Phase A)

> Author persona: **15-year Brent-WTI relative-value PM. Ex-physical Atlantic
> basin, currently running a book that trades Dated Brent / WTI-Houston /
> WTI-Midland, DFL term structure, plus a light 3-2-1 crack overlay. Read
> the code with a risk-committee mindset: "what could blow up if a junior
> trader clicked 'execute' on this?"**

## TL;DR

The stats layer is clean — `compute_spread_zscore` with the EWMA sidecar is a
real improvement over a lot of vendor tooling, the guardrails in
`_apply_guardrails` are adult, and the rule-based fallback means nothing
silently lies when Azure is down. But the thing you are backtesting and
signalling on is **not a trader-realistic Brent-WTI spread**. It's two
yfinance continuous-front-month series subtracted from each other, with
no roll adjustment, no expiry-day boundary, no basis decomposition, and
a fill model that is literally zero slippage / zero commission by
default. Anything Sharpe that comes out of this should be read as an
upper bound of what you'd ever see in the real book — and because of the
roll artefact, potentially a **biased** upper bound, not just a lossless
one.

Everything else (Cushing wiring, COT plumbing, crack wiring, catalyst
gating) is fine as scaffolding; the risk is that the PnL number on the
hero card is louder than the caveats.

---

## Findings — severity ranked

### S1 (Blocker) — Continuous front-month subtraction with no roll adjustment

**Files:** `providers/_yfinance.py:25-27,65-66`, `quantitative_models.py:50`,
`thesis_context.py:146`.

`fetch_daily` pulls `BZ=F` and `CL=F` — those are Yahoo's **continuous
front-month stitched** series. On every expiry (`CL` = ~3rd business day
before 25th of the prior month; `BZ` = last business day of month 2
prior), Yahoo swaps to the new front. The price level jumps by the
calendar spread — for WTI the M1–M2 has been anywhere from +$0.30 to
–$2.50 in the last three years (contango vs backwardation), for Brent
typically smaller. **None of that is adjusted for** anywhere between
`_yfinance.py:45` (`df = close[["Brent", "WTI"]].copy()`) and
`quantitative_models.py:50` (`df["Spread"] = df["Brent"] - df["WTI"]`).

Result: on 12 roll days per year per leg (so ~24 days a year), the
spread prints a fake $0.30–$2 gap that has nothing to do with supply,
demand, Cushing, or anything a thesis can cite. `backtest_zscore_meanreversion`
treats those as real bars and happily opens/closes trades against them.
The EWMA in `compute_spread_zscore:60-62` then amplifies the artefact
into the "real sigma" Z — that's a backtest mirage.

Fix: either (a) switch to panama-adjusted continuous series (back-adjust
the legacy history by the roll delta), or (b) drop the bar on roll day
+ roll day−1 for each leg, or (c) actually hold M+2 and roll explicitly
so the PnL includes the roll cost you'd really pay. I'd vote (a) for
signal + (c) for the backtest.

### S1 (Blocker) — Fill model assumes mid-price, zero slippage, zero commission by default

**File:** `quantitative_models.py:248-253, 315-317`.

```
slippage_per_bbl: float = 0.0,
commission_per_trade: float = 0.0,
```

The defaults are zero. The PnL we're showing on the dashboard and
feeding into `ThesisContext` (via `backtest.get("win_rate")` /
`bt_sharpe` at `thesis_context.py:210-214`) is therefore a **gross,
mid-priced, no-cost** number. On a BZ/CL outright, round-trip cost on
a real desk is roughly:

- exchange + clearing: ~$2–$2.50 per contract per leg = ~$0.005/bbl
  round-trip each leg
- bid-ask crossing on either leg at the close: 1 tick = $0.01/bbl,
  spread-on-spread is more like 2–3 ticks round trip
- roll cost (see S1 above): not modelled

At `entry_z=2` on a ~$0.60 std spread, gross $1.20/bbl targets get
chewed to ~$1.00–$1.10/bbl net very fast. On the 10,000 bbl default
notional (`quantitative_models.py:250`) that's a $1k–$2k difference per
trade, which flips the sign of the marginal Z thresholds. The knobs
exist but are off by default. `walk_forward_backtest` (line 424) and
`monte_carlo_entry_noise` (line 481) propagate the same zero defaults
— so the robustness checks are also gross-of-costs.

Fix: set realistic defaults (`slippage_per_bbl=0.02`,
`commission_per_trade=2.50`), and have the UI expose a "costs" toggle
rather than a true zero. Also — the slippage is applied flat per bbl
(line 316); in reality spread trades on illiquid back months are wider.
Consider scaling slippage by `Spread_EwmaStd` if you care.

### S1 (Blocker) — Daily-bar signal with intraday execution fiction

**Files:** `quantitative_models.py:301-331`, `data_ingestion.py:50-52`,
`providers/_yfinance.py:65-66`.

The backtest iterates **daily bars** (`for date, row in df.iterrows()`
at line 301) and assumes entry at the close spread `s = float(row["Spread"])`
and exit at the next qualifying close. Fine for research. But the
thesis card in `trade_thesis.py` + `thesis_context.py` is pitched to a
trader **during session** — and the intraday path in
`fetch_pricing_intraday` returns 1-min bars with a **~15 min publisher
delay** (comment at `_yfinance.py:59`, plus the 15-min lag is noted in
`data_ingestion.py:43`). The implementation shortfall between
"model fires at daily close Z = 2.1" and "trader sees it 15 min late
on intraday" is not modelled anywhere.

The `catalyst_clear` checklist item (`trade_thesis.py:319-321`) gates
EIA at 24h but there's no analogous gate for the 15-min intraday
latency, which is where the real slip lives — CLc1 can move 40¢ in
15 minutes on API/EIA prints (see S2 below on `_hours_to_next_eia_release`).

Fix: either restrict backtest entries to "next-day open" instead of
same-day close (a one-bar lag), or explicitly label signal latency in
the thesis output. The current setup pretends the signal and the fill
are simultaneous.

### S2 (High) — Spread PnL treats Brent and WTI as 1:1 bbl with no hedge ratio

**Files:** `quantitative_models.py:314`, `trade_thesis.py:356-380`,
`thesis_context.py:238`.

`gross_per_bbl = (s - entry_spread) * position` at line 314 implicitly
assumes the trade is "1 bbl Brent vs 1 bbl WTI." A cointegration hedge
ratio is computed and stored (`coint_info['hedge_ratio']`, surfaced on
`thesis_context.py:238` into `coint_hedge_ratio`), but the backtest
never reads it — look at `backtest_zscore_meanreversion`'s signature
(line 246): no hedge ratio parameter. The thesis decoration in
`decorate_thesis_for_execution` (`trade_thesis.py:356-381`) also just
says "long CL=F / short BZ=F" 1:1, regardless of what the hedge ratio
came out to be.

In reality during a structural break (Q1 2022 Urals, Q3 2015 export-ban
lift) the hedge ratio drifts to 0.7–0.8; running 1:1 is running a
directional oil bet dressed as a spread trade. The code *knows* this
(the `not_cointegrated` clamp at `trade_thesis.py:449-464` caps
conviction at 5), but only the conviction number changes — the
suggested instruments, sizing, and backtest PnL are all still 1:1.

Fix: thread `coint_hedge_ratio` through `backtest_zscore_meanreversion`
and into the Tier 3 futures rationale. "Long 7 CL=F / short 10 BZ=F"
is the real ticket.

### S2 (High) — Physical vs financial spread drivers are conflated in the thesis context

**File:** `thesis_context.py:121-165`, `providers/_eia.py:37-40,206-242`.

The inventory tile drives `inventory_4w_slope_bbls_per_day` from
`Total_Inventory_bbls` (Commercial + SPR, at `_eia.py:239`) — so SPR
releases (purely a policy lever, zero physical-market signal for the
Brent-WTI spread) contaminate the slope. The thesis is told "inventory
draws at X bbls/day" and ascribes Brent-WTI narrative to it. That's
wrong: SPR going out the door does *nothing* to the Brent-WTI spread
except via the Cushing delivery hub. And crucially, Cushing is tracked
separately (`_SERIES_CUSHING` at `_eia.py:40`) — we already fetch it
— but in the thesis context's driver slopes we only compute the 4-week
Cushing slope at `thesis_context.py:161-165` and leave the headline
driver as Commercial+SPR total.

Worse, SPR series is ffilled aggressively at `_eia.py:229` so a stale
value can bleed into `Total_Inventory_bbls` at line 239 for weeks.

Fix: for Brent-WTI specifically, the thesis should be weighting Cushing
(and PADD 2 / PADD 3 differential) far higher than total-US. Consider
making `inventory_4w_slope_bbls_per_day` a Cushing-only or a weighted
blend, and separate a second field `total_us_slope` for context only.
Also: split the `days_of_supply` calculation — right now at
`thesis_context.py:128-132` it's days-until-floor using total inventory
with an arbitrary `floor_bbls`; on a desk that's a macro tile, not a
Brent-WTI spread tile.

### S2 (High) — WTI-Houston vs WTI-Midland basis is absent entirely

**Files:** `providers/_yfinance.py` (no tickers), `trade_thesis.py`
(no reference).

The Brent-WTI spread a trading desk cares about in 2026 is really
three spreads stacked: Dated Brent − WTI-Houston (FOB USGC), WTI-Houston
− WTI-Midland (pipe tariff), WTI-Midland − NYMEX WTI (Cushing basis).
The code conflates the whole stack into `BZ=F − CL=F`. That's the
*NYMEX proxy* spread, not the traded-on-a-desk spread. `MEH` (WTI
Houston) and `WTL` (Midland) both have listed futures on NYMEX (HCL,
WTL) with reasonable liquidity.

For a research tool this is acceptable as a v1 simplification, but the
thesis prose should not claim to be speaking about *the* Brent-WTI
arb when the arb has three legs it can't see. At minimum: caveat in
`trade_thesis.py`'s SYSTEM_PROMPT (line 214) that the spread is NYMEX
proxy, not physical.

### S2 (High) — Hours-to-next-EIA ignores DST and holidays

**File:** `thesis_context.py:67-84`.

`_hours_to_next_eia_release` hard-codes `candidate = now.replace(hour=14, minute=30, …)`
and uses `(2 - now.weekday()) % 7` — it assumes EIA always prints at
14:30 UTC. In summer (EDT) EIA prints at 14:30 UTC = 10:30 EDT, but in
winter (EST) it prints at 15:30 UTC = 10:30 EST. The comment at line
71-72 flags this ("DST differences are not accounted for") — so this
is a known bug, fine, but the downstream consequence is that
`catalyst_clear` (`trade_thesis.py:303-307`) is wrong by ±1 hour for
half the year. At the boundary (22-26 hours from print), a trader
clicks the box thinking there's clearance, and the print hits mid-fill.

Also: EIA skips federal holidays and slides the release to Thursday
(Independence Day, Thanksgiving, Christmas, New Year). None of that is
modelled. On those weeks the checklist will ring false-clear.

Fix: compose with `pandas_market_calendars` or a hard-coded EIA
deferred-release table. Low effort, reduces a real tail risk.

### S2 (High) — Intraday 1-min bars dropna'd to "shared timestamps" creates silent survivorship

**File:** `providers/_yfinance.py:71-80`.

```
df = pd.DataFrame({"Brent": brent["Close"], "WTI": wti["Close"]})
df = df.dropna(how="any")
```

Brent (ICE) and WTI (NYMEX) trade on different session calendars —
ICE runs different maintenance minutes, and during US holidays ICE
prints while NYMEX doesn't (and vice versa). `dropna(how="any")`
silently removes every bar where only one side printed. That creates
gaps that look like flat-spreads in the live dashboard. For the
backtest path we don't care (daily), but the thesis' "session_is_open"
flag (`thesis_context.py:194-199`) treats the two markets as one
NYMEX session, which is wrong — Brent doesn't care about NYMEX's
5pm ET close. Non-blocker, but during the Good Friday / MLK gap this
visibly misbehaves.

### S3 (Medium) — Sharpe annualisation uses sqrt(365/mean_hold_days)

**File:** `quantitative_models.py:351-355`.

The annualiser is `sqrt(365 / mean_hold)`, which treats trades as
i.i.d. and ignores overlap. If the average hold is 5 days, that's
sqrt(73) ≈ 8.5× — reasonable-looking, but silently wrong when trades
overlap (they don't here because the position flag is 0/±1) or when
trade count is small. On 6 trades a year the annualiser is fine; on
50 with a 2-day average it inflates. Also: calendar days, not trading
days — `sqrt(252/mean_hold_trading_days)` is the desk convention.

Not a blocker, but the Sharpe on the hero card is technically flattering.

### S3 (Medium) — Cointegration guard only clamps conviction, doesn't gate entry

**File:** `trade_thesis.py:449-464`, `quantitative_models.py:246`.

If Engle-Granger fails (`coint_verdict == "not_cointegrated"`), the
guardrail knocks conviction down to 5 and prints a caveat. It doesn't
stop the backtest from being run, and `backtest_zscore_meanreversion`
has no input parameter for "only enter when cointegrated over the last
N bars." On a desk, cointegration-broken regimes are when you *stop
trading mean-reversion*, not when you size down by 50%. The conviction
clamp is pulling in the right direction but half-measure.

Fix: expose an `entries_require_coint: bool = True` flag on
`backtest_zscore_meanreversion`, filter the iteration window to dates
where a rolling E-G p-value is below some threshold, and surface both
"full" and "coint-gated" equity curves to the UI.

### S3 (Medium) — COT positioning fetched but not folded into the backtest

**Files:** `providers/_cftc.py:206-221`, `thesis_context.py:167-188`,
`quantitative_models.py:246` (no reference).

The CFTC plumbing is solid (and I like the 3-year MM Z-score). It
lands as a context field for the LLM and that's it. `backtest_zscore_meanreversion`
ignores it. One of the more robust Brent-WTI signals in the last
decade is "MM extreme-long WTI + Z-score blown = fade". Folding
`cftc_mm_zscore_3y > 2` as a *corroborating* entry filter would
probably lift the hit rate by 5-10 pts. At minimum, run the
walk-forward restricted to weeks where MM is at a percentile extreme
and report the subset stats — same engine, different slice.

### S3 (Medium) — Seasonality and hurricane-season flags absent

**Files:** `thesis_context.py` (no reference), `trade_thesis.py`
(no reference).

Brent-WTI has a real seasonal: refinery turnaround spring (Feb-Apr) +
autumn (Sep-Oct) compresses domestic crude demand → Cushing builds →
WTI weakens → spread widens. Hurricane season (Jun-Nov) is a two-way
bet on USGC refinery vs crude logistics. None of that seasonality is
encoded, so the LLM has to infer it from raw numbers. Adding
`month_of_year` and a `turnaround_season: bool` / `hurricane_season: bool`
field to `ThesisContext` (`thesis_context.py:201-257`) is a 10-minute
change that would noticeably sharpen thesis prose. For the backtest,
a seasonal-dummy interaction term could drop the parameter sensitivity
Monte Carlo (`monte_carlo_entry_noise`, line 481) shows.

### S3 (Medium) — Depletion forecaster uses 4 weekly points to project 3 years

**File:** `quantitative_models.py:73-158`.

`forecast_depletion` fits `LinearRegression` on 4 weekly observations
by default (`lookback_weeks: int = 4` at line 76) and projects out to
`end_date = pd.Timestamp(t0) + timedelta(days=365 * 3)` at line 142.
Four points cannot support a three-year linear extrapolation — the
R² on line 127 is going to be noise-dominated, and any stray week (e.g.
a post-hurricane rebuild) flips the slope sign entirely. The projected
floor date feeds into the inventory tile and into the LLM context.

On a desk this would get laughed at. Fix: either raise the default
lookback to 13–26 weeks, or cap the projection horizon at
`3 × lookback_weeks`, whichever is shorter. Also consider a
non-parametric seasonal STL decomposition before regressing — a
4-week slope in March is noise; in November it's draw season.

---

## What's right, keep it

- The EWMA Z sidecar at `quantitative_models.py:60-65` — exactly the
  right instinct, λ=0.94 is the convention. Rolling std alone lags.
- Guardrails in `trade_thesis.py:389-469` — inventory-missing → flat,
  weak backtest → conviction cap, vol percentile → size clamp. That's
  desk discipline.
- Audit JSONL at `trade_thesis.py:725-743` — gold for post-hoc
  hit-rate tracking. Never break this.
- `context_changed_materially` (`trade_thesis.py:774-808`) — not
  burning tokens on millisecond noise is grown-up.
- Crack spread wiring (`crack_spread.py:71-147`) is correctly scaled
  (gal→bbl via 42 on line 120) and the 30d Δcrack vs Δ(Brent-WTI)
  correlation is exactly what a refining-driven narrative needs.

## Bottom line

Phase A status: the **statistics** are defensible for a research tool.
The **trade realism** is not yet at a level where I'd wire PnL-weighted
sizing off this output. Before Phase B I'd close S1-1 (roll adjust),
S1-2 (fill model), and S1-3 (daily→next-open lag). The S2 items are
credibility-of-thesis issues; they make the LLM prose sound smart
about things it can't actually see.
