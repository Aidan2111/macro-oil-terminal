# Quant desk review — macro-oil-terminal, v0.3

> Author persona: **"K. Nikolic" — 15y on a Brent-WTI relative-value desk, ex-physical trader,
> currently runs a book that trades the Dated Brent / WTI-Houston / Midland arb plus
> term-structure and crack legs. Reviewed the terminal with a trade ticket in mind,
> not an academic lens. Graded it like I'd grade an analyst presenting the book
> to me on a Monday morning.**

## TL;DR

The terminal is a **surprisingly grown-up research toy**. The UX is cleaner than
half the vendor platforms I pay for; the plain-language relabel is correct
(*nobody on the desk says "Z-score"*). The AI thesis card is a serious idea
executed better than I expected — the fact that it won't speculate without
inventory loaded, that it caps sizing, that it logs every call — that's real
discipline.

But as a **decision-support tool on a live desk** it's still missing foundations
a quant PM would want before giving it any meaningful notional. The two biggest
gaps are (a) **no cointegration test** — a mean-reversion signal on a pair that
isn't cointegrated is a random number generator — and (b) **no Cushing
inventory isolation**, which is where 70% of the Brent-WTI spread volatility
actually lives. Everything else flows from those two.

## Methodology

I walked the four tabs, clicked every button, opened every expander, and then
pretended I needed to produce a trade recommendation off it by 10:30 ET on a
Wednesday. I also read `trade_thesis.py`, `quantitative_models.py`, and
`thesis_context.py` end-to-end looking for look-ahead bias, expiry/roll
handling, and boundary cases.

## What's **right** (don't break these)

1. **Plain-language labels with a technical escape hatch.** The Advanced
   Metrics toggle is the correct primitive.
2. **Structured JSON schema on the thesis.** The guardrail layer (clamp
   conviction vs backtest hit rate, force flat when inventory missing, cap
   sizing at 20%) is what separates a trade tool from ChatGPT roleplay.
3. **Materiality-based regen.** Most vendor tools burn tokens on every mouse
   move. This doesn't.
4. **Audit JSONL.** Gold for post-hoc hit-rate tracking — keep this.
5. **No simulator in prod.** The `InventoryUnavailable` error-with-retry is
   correct. Don't ever revert that.

---

## Ranked punch list (impact / engineering hour)

Ordering is **PM-value per engineer-hour** — not difficulty, and not
CS-elegance.

### Tier A — must-fix before I'd trade off this

1. **Cointegration test** *(est: 4h)*
   The mean-reversion backtest assumes Brent and WTI are a stable pair. They
   usually are, but during structural breaks (2015 export ban lift, 2022
   Russia/Urals, Q3 2025 WCS differential blowout) they *de-cointegrate* for
   weeks at a time. Need an **Engle-Granger test on rolling windows**, with
   the Dickey-Fuller p-value on the residual shown as a tile, and the thesis
   card suppressed (or re-framed as "trend follow" rather than "snap-back")
   when p > 0.10 over the last 60 sessions. This is the single highest-value
   upgrade.

2. **Cushing-specific inventory** *(est: 3h)*
   Total US inventory is a blunt proxy. The Brent-WTI spread is mechanically
   driven by **Cushing delivery hub** utilization — when Cushing fills, WTI
   weakens (can't get it out), spread widens. When Cushing drains, WTI
   firms, spread collapses. Add `W_EPC0_SAX_YCUOK_MBBL` (Cushing stocks)
   from EIA dnav as a dedicated tile and as a thesis-context field.
   Headline inventory stays but is secondary.

3. **Vol-normalized dislocation** *(est: 4h)*
   Current dislocation is `(spread - mean_90d) / std_90d`. That std is a
   rolling window — it *lags* regime change. In a vol spike the denominator
   balloons a day late and we get fake-calm readings. Swap in a **GARCH(1,1)
   residual std** (or simpler: EWMA-of-squared-residuals with λ=0.94). Show
   both in advanced view. Quant-desk convention is "this is the real sigma,
   not the moving average."

4. **Risk metrics upgrade** *(est: 2h)*
   Sharpe is a starting point. Add:
   - **Sortino** (downside deviation only — matters because the strategy
     has fat left tails when cointegration breaks)
   - **Calmar** (return / max DD — the number a PM cares about for sizing)
   - **VaR-95 / ES-95** on per-trade PnL distribution
   - **Rolling 12m Sharpe** — shows when the regime changed

5. **Crack spread context** *(est: 3h)*
   If refining margins are blown out, WTI can trade firm vs Brent purely
   because US refiners are lifting light sweet. The thesis card should know
   that. Pull `RB=F` (RBOB) + `HO=F` (heating oil) + `CL=F` (WTI), compute
   **3-2-1 crack = (2·RBOB + HO) / 3 − WTI**, and feed current crack level
   + 30d rolling correlation vs Brent-WTI into the context JSON.

### Tier B — upgrades that separate a toy from a tool

6. **CFTC Commitment of Traders for CL + BZ** *(est: 6h, weekly data)*
   Non-comm net positioning is *the* consensus-positioning signal. If the
   thesis is "long spread" but non-commercials are already 90th-percentile
   long WTI, that's a red flag. Pull CFTC weekly disagg on Tuesday for
   Friday-prior.

7. **Dynamic hedge ratio (Kalman filter)** *(est: 1d)*
   Right now the implicit hedge is 1:1 (long 1 BZ, short 1 CL). In reality
   the hedge ratio drifts (varies 0.85–1.15 historically). Fit a Kalman
   filter on `Brent_t = α_t + β_t · WTI_t + ε_t`, use β_t as the hedge
   ratio. Surface as "hedge ratio: 1.07" on the card.

8. **Term-structure (carry)** *(est: 1d)*
   The backtest ignores roll cost. Entering a long-spread trade when Brent
   is in contango and WTI in backwardation means you bleed even if you're
   right. Pull the 1m/3m/6m/12m curves for both and compute carry-adjusted
   PnL. This alone will shift the "hit rate" downward and make the numbers
   honest.

9. **Regime-switching model (2-state HMM)** *(est: 1d)*
   "Normal" regime (mean-reversion works) vs "stressed" regime (trend-follow
   or stand aside). Fit a 2-state Gaussian HMM on first-differenced spread.
   When the model is in the stressed state, clamp thesis conviction ≤ 4.

10. **VLCC / Suezmax freight rates** *(est: 4h — public Baltic Exchange data)*
    Shadow-fleet and sanctions arb move ***through*** tanker rates. Wire
    Baltic Dirty Tanker Index (BDTI) + TD3C (VLCC Middle East–China) +
    TD20 (Suezmax West Africa–Europe). Show as a "freight pressure" tile.
    When BDTI is 80th-percentile+ the shadow category cargoes get more
    active, which usually correlates with Brent firming vs WTI.

### Tier C — adds polish, not edge

11. **Strait of Hormuz satellite/AIS traffic tracker** *(est: 2d)*
    Keeps the "fleet analytics" tab honest. aisstream.io with a bounding
    box around the Strait, live vessel count. Geopolitical shocks move
    this tile within hours.

12. **Urals / ESPO discount** *(est: 4h)*
    Urals is the marginal Russian crude; ESPO is the pacific equivalent.
    When discounts blow out, the "sanctioned flags" cargo volume in Tab 3
    becomes more valuable information because it's actually priced.

13. **Refinery maintenance calendar seasonality** *(est: 1d)*
    EIA publishes utilization. Seasonal pattern is predictable (Feb–Apr
    turnarounds, Aug maintenance). The thesis card should know a spread
    move in Feb is 60% likely to be maintenance-driven, not structural.

14. **Product inventories (gasoline, distillate)** *(est: 2h — same EIA dnav)*
    Secondary signal. High gasoline inventory = low crack = light-sweet
    demand soft = WTI soft. Don't skip this.

15. **Open interest + volume on CL + BZ** *(est: 3h)*
    Thin market = spread can gap. Tell the thesis when liquidity is <40th
    pct of trailing year so it can caveat sizing.

16. **WTI-Houston vs Midland basis** *(est: 1d)*
    Inside the US, the basis at Midland (upstream) vs Houston (waterborne)
    is where the real physical action is. When Midland–MEH blows out, the
    Brent-WTI spread is about to move.

17. **Scenarios / what-if slider** *(est: 1d UX)*
    "If Cushing draws 5 MMbbl next week, what does the thesis say?" Lets
    the PM stress their own hypothesis against the model.

### Subtle bugs / correctness concerns I spotted

- **Expiry / roll handling.** yfinance `CL=F` / `BZ=F` are front-month
  continuous contracts — at roll they can have discontinuities of
  $0.10–$1.50 that the spread Z-score will read as "dislocation." The code
  doesn't detect rolls or adjust. *Risk: false alerts mid-quarter.*
  Fix: flag when first-differenced spread > 5σ and exclude from the
  rolling window or mark the bar.
- **Weekend/holiday handling.** The `session_is_open` flag is a rough
  approximation. Good enough for now, but noting it: *Veterans Day,
  Thanksgiving Thursday-Friday, Christmas Eve, Boxing Day* are all
  half-days where the spread gets weird because one side trades and one
  doesn't.
- **Look-ahead leakage in the backtest.** The `_spread_cached` uses the
  full frame to compute the rolling mean/std, which is fine for point-in-time
  evaluation only if the rolling window is strictly past-looking.
  `compute_spread_zscore` uses `.rolling(window=90)` which is left-aligned
  (past-only) — so this is **clean**. Kept checking because this is where
  90% of backtest bugs live.
- **Survivorship bias.** Not applicable here (it's a pair trade on the two
  liquidest crude contracts in the world; no delisted tickers). Pass.
- **Timezone handling.** `fetched_at` uses `pd.Timestamp.utcnow()`,
  `last_refreshed` displays in UTC — consistent. Good.
- **Backtest "0 commission / 0 slippage" default** now has a 0.05/bbl +
  $20/rt default which is realistic for CL; a little thin for BZ which is
  wider. Fine for a demo; flag for the PM.

### Data pipeline gaps (summary table)

| Source | What it gives | Cost | Effort |
|---|---|---|---|
| EIA Cushing series | The single most predictive inventory | free | 3h |
| CFTC disagg COT | Positioning consensus | free (weekly) | 6h |
| Baltic Exchange BDTI/TD3C/TD20 | Freight pressure | free-ish | 4h |
| yfinance RB=F / HO=F | Crack spread | free | 3h |
| Urals / ESPO differentials | Sanctions-fleet pricing | S&P Global subscription | 1d+ |
| Refinery utilization | Seasonal spread driver | EIA free | 1d |
| Midland-MEH basis | Intra-US pipeline signal | Platts/Argus sub | skip until needed |
| BorderlessAIS Strait of Hormuz | Geopolitical shock | key gated | 2d |

### Trading-desk UX wishlist (I'd pay real money for these)

- **Risk tile pinned at the top.** Current: you have to click into the AI
  tab to see your stance. Wanted: a 1-line risk summary above all tabs —
  `LONG SPREAD · 7.2 conv · entry 3.40σ · stop 5.5σ · dislocation NOW +2.1σ
  · next EIA Wed 10:30 ET`.
- **Keyboard shortcuts.** `1/2/3/4` for tab switch. `R` for regenerate.
  `/` focuses a filter. `?` for cheat sheet. A desk user won't click if
  they can press a key.
- **Blotter as a real table.** Trade blotter is hidden inside an expander;
  it should be promoted and include fill price, holding period, PnL,
  drawdown contribution — in that order. Sortable by PnL.
- **Catalyst countdown.** Instead of showing "2026-04-22" next to an EIA
  event, show "**in 6h 14m**." The desk thinks in countdowns.
- **Dark/light toggle.** 80% of sell-side desks are light theme. Streamlit
  theming supports it — just expose a toggle.

### Things the AI thesis does well that I want kept

- Calling out when backtest hit rate <55% and clamping conviction.
- Forcing disclaimer_shown = true.
- Not trying to tell me what to do when inventory is missing (you have no
  idea how many tools will happily hallucinate a thesis on stale data).
- The "what changed" diff on regenerate is *exactly* what a PM wants on a
  re-read 30 minutes later.

### Things I'd remove / demote

- The "Email me on Z-score breach" toggle. Nobody runs a desk off email
  alerts anymore. Replace with Slack webhook or at minimum hide behind a
  "power user" fold.
- The 3D WebGPU globe is cute — but on Tab 3 it pushes the actually-useful
  flag-state drill-down below the fold. Move the globe to a collapsed
  expander, pull the drill-down chart up.

---

## Verdict for the PM

**Give it a $500k notional sleeve on a discretionary overlay book**, not a
production mandate. Treat it as decision support + post-trade audit (the
JSONL thesis log is a real asset). Revisit after items **1–5** from the
punch list are shipped, then it's worth a $5m sleeve.

*Keep it away from new grads until tier A lands* — the current card looks
confident enough to over-weight it.

— *K.N., head of Brent-WTI RV. 2026-04-22.*
