# Quant desk review — pass 2 (post Tier A+B shipment)

> Same persona: **K. Nikolic** — re-opened the dashboard after the
> engineering team shipped the first five-item punch list plus the
> Tier-B start (Twelve Data + Polygon pricing fallback + desk UX).
> Writing this the same way I'd write a second-look for an external
> vendor I'm renewing: what's better, what's still weak, what moves
> next.

## What improved materially

1. **Cointegration tile is real and tied to guardrails.** The "BROKEN"
   badge (p ≥ 0.10) actually suppresses thesis conviction via the
   `_apply_guardrails` clamp — I tested by poking `coint_verdict =
   "not_cointegrated"` in a fixture and the stance was clamped at
   5/10 with the right caveat. That's the single highest-value upgrade
   from pass 1 and it landed cleanly.
2. **Cushing tile.** I now see 463/409/41 Mbbl (commercial/SPR/Cushing)
   instead of "US inventory" collectively. This is how a desk actually
   thinks about the WTI leg.
3. **Risk suite.** Sortino + Calmar + VaR-95 + ES-95 + 12m-rolling
   Sharpe — this is *the* set I'd have asked for. Calmar especially —
   PMs love that one metric because it sizes a book.
4. **3-2-1 crack tile + 30d corr.** The correlation delta is the
   tell-tale — if it's >0.3 and positive, the Brent-WTI move is refining
   economics, not structural.
5. **Pinned risk bar.** The countdown to the next EIA Wednesday is
   exactly what I asked for. Hotkeys work.
6. **Data sources health panel.** A 🟢/🔴/⚪ strip behind every dependency
   is what vendor monitoring looks like. Well done.

## What I still want (next top 5, ranked)

### Tier A — promote these now

1. **CFTC disaggregated COT positioning** *(est: 6–8h)*
   Still missing. Non-commercial net positioning is the consensus
   sanity check on any spread trade. Tuesday 3:30 PM ET publishes
   Friday-prior; cache it. Two new thesis-context fields:
   `noncomm_wti_pct_net_long`, `noncomm_brent_pct_net_long`. The LLM
   should cite this when conviction > 7 ("consensus is already this
   way; beware the crowded trade").

2. **Dynamic hedge ratio from Kalman filter** *(est: 1d)*
   Engle-Granger gives a *static* β. Today's regime shifts that β
   weekly. Fit a Kalman filter on `Brent_t = α_t + β_t · WTI_t + ε_t`,
   surface β_t as a tile + send into thesis context so the LLM knows
   the hedge has drifted. I'd demote the static OLS β and promote the
   Kalman β as the primary.

3. **Roll-adjust / carry-aware backtest** *(est: 1d)*
   The backtest numbers look great (100% win rate, Sharpe 5.01) and
   that's a red flag. Front-month `CL=F` and `BZ=F` roll-jump once a
   month. If we include those jumps as "dislocation" we're reading
   manufactured signal. Two ways to fix:
   a. Pull the 2nd-month contracts and build a truly continuous series.
   b. Detect bar-over-bar moves > 5σ and exclude from the z-score window.
   Either way, honest backtest numbers will drop Sharpe below 2 and the
   product will feel more trustworthy.

4. **Trade blotter as a first-class panel, not expander** *(est: 4h)*
   Still tucked inside an expander. I asked for it promoted. Make it a
   separate sub-tab under "Spread dislocation" with: entry date, exit
   date, side, entry spread, exit spread, PnL, drawdown contribution,
   holding days. Sortable by PnL. This is the table a PM stares at.

5. **Weekly petroleum status CSV** *(est: 2h, but huge data lift)*
   Right now we lean on the dnav LeafHandler scrape. EIA also publishes
   the weekly summary table as a CSV mirror at
   `https://ir.eia.gov/wpsr/psw05.xls`. This gets us product inventories
   (gasoline, distillate, jet) in a single pull. Not decision-critical
   in isolation but gives the thesis more breadth — high distillate =
   low crack = WTI soft.

### Tier B — would be nice

6. **Historical hit-rate tracker on the thesis log** *(est: 6h)*
   We're now 30+ theses into `data/trade_theses.jsonl`. Build a
   tracker: for each closed thesis, did the spread actually revert
   toward the stated target within the stated horizon? Show a
   "Thesis track record" card — hit rate, average hold vs predicted
   hold, "most recent mistake" line. This is what separates a vendor
   demo from a tool worth paying for.

7. **Vol-regime-aware guardrail** *(est: 2h)*
   We compute `vol_spread_1y_percentile` but don't use it in
   guardrails. When percentile > 85 ("high-vol regime"), size ≤ 2% of
   capital regardless of what the model says. Add a third clamp
   alongside the cointegration-broken and weak-backtest ones.

8. **Live Slack webhook for breach alerts** *(est: 3h)*
   The email toggle is still there. Demote it to advanced view and
   add `SLACK_WEBHOOK_URL` alongside — that's where desks actually
   consume alerts. Same breach logic, nicer delivery.

9. **Spread term structure tile** *(est: 4h)*
   Front-month Brent-WTI is one number. Pull M+1, M+2, M+3 Brent-WTI
   and show the **spread curve**. When the curve is steeply backwardated
   or contangoed the thesis conviction should modulate.

10. **Quote-of-Day annotation on thesis card** *(est: 1h, low-effort UX)*
    On the thesis card, render one line that rotates: "EIA released 6
    hours ago — current spread is +0.3σ above the pre-release level."
    "Dislocation has held > 2σ for 4 of the last 5 sessions." Tiny, but
    gives the card a liveness.

### Bugs I want fixed

- **Ticker strip flickers on reload.** The `st.fragment(run_every=60)`
  refreshes the whole strip, not just the numeric text. On a slow
  mobile connection you see the sparklines redraw from scratch. Move
  the sparklines out of the fragment and keep only the number + alert
  badge inside.
- **`keep-warm` is 5-min cadence.** Even I can tell from the Azure
  response time it's overkill. Move to 10-min during waking hours;
  add a longer cadence (30-min) for the overnight US off-peak window.
  Saves CPU minutes on the free tier.
- **Thesis "Copy as markdown" button is huge.** Should be a small
  download icon, not a primary button. It competes with Regenerate
  visually.

## Process observation

The fact that the engineering team dropped a full ADR log alongside
the features is a strong signal. Eight months from now when someone
joins the team and asks "why is that field called dislocation not
Z-score?" the answer is one grep away. Keep doing that.

## Sizing verdict

Pre-pass-1: $500k sleeve on a discretionary overlay.
Pre-pass-2 (after top-5 landed): **$5m sleeve** once items 1–3 above
also ship (CFTC positioning, Kalman hedge, carry-aware backtest).
Items 4–5 are quality-of-life, not sizing-gated.

— *K.N., head of Brent-WTI RV. 2026-04-22, second look.*
