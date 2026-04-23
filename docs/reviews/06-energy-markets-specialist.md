# 06 — Energy Markets Specialist review (Phase A)

> Persona: 12 years on a physical crude desk — Dated Brent window, Midland-to-Houston
> arb, freight, and refinery margin pairs. I don't care about your Python, I care
> whether the signals you're feeding the model describe the **barrel**. Brent-WTI
> is not a statistical pair — it's a pipeline, a ship, a refiner, and a sanctions
> regime. If the model can't see those, its "dislocation" is just noise around a
> structural break it doesn't know exists.

## TL;DR

The terminal has picked up Cushing (good), 3-2-1 crack (good), and CFTC managed-money
positioning (good) — but the **physical structural layer is missing almost entirely**.
There is no Midland-Houston differential, no WTI-Houston export netback, no freight
(VLCC/Suezmax TCE), no product inventory (gasoline/distillate), no OPEC+ compliance
read, no sanctions flow quantification, and no Strait-of-Hormuz / Bab-el-Mandeb
disruption proxy. The fleet widget categorises flag states as `Sanctioned` but never
wires tonnage into the thesis as a sanctioned-flow indicator. Worst of all, the
crack spread is computed (`crack_spread.py:118-120`) but only surfaces a single number
and a 30-day correlation — refinery economics, which *cause* a large share of WTI
moves, are under-cited in the prompt. Below, severity-ranked.

---

## Findings

### 1. [CRITICAL] No Midland-Houston / WTI-Houston differential — the actual WTI driver

`providers/_eia.py:37-40` pulls `WCESTUS1` (commercial), `WCSSTUS1` (SPR) and
`W_EPC0_SAX_YCUOK_MBBL` (Cushing). Cushing is the NYMEX delivery point, fine —
but ~60% of Brent-WTI volatility since 2020 has lived in the **Midland-Houston
differential** and the **WTI-Houston / Brent (MEH-Brent) netback**, not in Cushing.
When USGC export arb is wide, Permian barrels bypass Cushing entirely and WTI at
Cushing can sit pinned while Brent-WTI blows out on the export leg. EIA publishes
`PET.RWTC.D` (WTI Cushing) and the MEH series; Argus/Platts Midland is paywalled
but the **EIA weekly export volumes** (`PET.WCREXUS2.W`) are free and are a usable
proxy for the arb's openness. The `_fetch_series` wrapper at `providers/_eia.py:174`
accepts arbitrary series IDs — adding `PET.WCREXUS2.W` and a Midland-Houston proxy
(e.g. `PET.RCLC1.W` minus `RWTC`) is three lines. Without it the model literally
cannot see the dominant WTI-side driver.

### 2. [CRITICAL] Product inventory (gasoline, distillate) missing — the refiner's lens

`providers/_eia.py:37-40` lists only crude series. EIA weeklies include
`WGTSTUS1` (motor gasoline stocks) and `WDISTUS1` (distillate stocks) on the exact
same dnav/v2 endpoints already wired at `_fetch_series`. Product draws *lead* crude
demand reads by one cycle — a distillate draw with flat crude stocks is unambiguously
bullish refining margins, which pulls WTI up faster than Brent because US refiners
are the marginal lifter. `thesis_context.py:122-132` exposes only
`Total_Inventory_bbls` = commercial + SPR. The LLM prompt has no field for product
inventory at all (`trade_thesis.py:44-114`). This is the single highest-leverage
data addition: two new series, two new `ThesisContext` fields.

### 3. [HIGH] No freight — VLCC/Suezmax TCE is the Brent-leg driver

The AIS pipeline at `providers/_aisstream.py:124-136` collects **positions**, and
`data_ingestion.py:123-162` categorises **flag states**, but **freight rates** —
the economic driver of the arb — are never read. When VLCC TCE on
TD3C (AG-China) spikes above $60k/day, Middle East crude lands in Asia at a
premium and Atlantic-basin Brent gets bid, which widens Brent-WTI independently of
anything happening at Cushing. Baltic Exchange publishes TD3, TD20 (WAF-UKC),
TD22 (USGC-China) routes; Howe Robinson and Clarksons have free weekly summaries.
None are wired. The model sees flag counts but not the dollar cost of moving a
barrel — it is blind to the single most important shipping variable.

### 4. [HIGH] OPEC+ compliance — no proxy, no prompt field

`thesis_context.py:201-257` lists 30+ fields; zero relate to OPEC+ production vs
quota. Monthly MOMR, Argus compliance tables, and the IEA OMR all publish member-
level production. Even a **single scalar** — "OPEC+ compliance % of pledged cut,
last reported month" — gated on a manual CSV upload would let the LLM differentiate
a $2 spread move driven by Saudi cheating versus one driven by Cushing draws. The
`ThesisContext` schema at `trade_thesis.py:96-114` explicitly documents "optional
— default to sentinels" additions, so adding `opec_compliance_pct: Optional[float]`
is schema-safe.

### 5. [HIGH] Sanctions flows computed but never plumbed to the thesis

`data_ingestion.py:70-82` and `quantitative_models.py:164-166` label Russia/Iran/
Venezuela vessels as `Sanctioned`, and `thesis_context.py:140` sums their
cargo into `fleet_sanctioned_mbbl`. But the **flow context** — is sanctioned
tonnage rising, falling, routing to India/China vs dark-destination? — is never
computed. `fleet_delta_vs_30d_mbbl` exists in the schema (`trade_thesis.py:77`)
but `thesis_context.py:227` sets it to `None` — the code that would populate
it isn't wired. A 30-day delta of sanctioned-flag tonnage is a legitimate leading
indicator of discount-crude absorption capacity (when India saturates, Urals
discount widens, Brent firms relative to WTI). Fill this field.

### 6. [HIGH] Crack spread is computed once, not as a time series of pressure

`crack_spread.py:71-147` returns `latest_crack_usd` and `corr_30d_vs_brent_wti`
— two scalars — via `ThesisContext.crack_321_usd` and `crack_corr_30d`
(`trade_thesis.py:102-103`). That's enough for the model to *mention* refining,
not enough for it to **reason** about it. What's missing: (a) **crack percentile
vs its own 1y history** — a $28 3-2-1 is bearish in summer and bullish in winter;
(b) **gasoline crack vs distillate crack split** (from the same RB/HO legs, trivially
derivable in `compute_crack` at `crack_spread.py:118`); (c) **Brent-based crack**
(`2·RBOB + HO)/3 − Brent`) for the Atlantic-basin refiner lens. Without (c), the
model sees US refining margin but not whether European refiners have an equal or
inverted incentive — which is exactly what moves the transatlantic arb.

### 7. [MEDIUM] Strait of Hormuz / Bab-el-Mandeb geopolitical premium — no proxy

The terminal has a fleet view (`data_ingestion.py:123`) and a flag-state
categoriser (`quantitative_models.py:182-240`) but no notion of **choke-point
transit density**. A simple count of tanker positions inside a Hormuz bounding box
(25-27°N, 55-57°E) divided by the rolling 30-day mean would give a live read on
Gulf tanker activity. The `_aisstream.py:37-42` subscription already uses bounding
boxes — adding a second key-region subscription and a `choke_point_transit_index`
field (sentinel-defaulted per the `ThesisContext` additions convention at
`trade_thesis.py:96`) is a natural extension. Right now the LLM has to infer
geopolitical premium from spread + volatility alone, which is precisely what
produces false "mean-reversion" signals during conflict windows.

### 8. [MEDIUM] EIA vs IEA reconciliation — one source, no convergence check

`providers/_eia.py` is the only inventory source and `providers/inventory.py` (not
read here but referenced at `data_ingestion.py:33`) wraps it. IEA OMR publishes
OECD stock data monthly with a ~6-week lag; the EIA STEO does the same on a US-only
basis. When EIA and IEA disagree on OECD stock direction (it happens ~quarterly),
the discrepancy itself is a signal — typically it means one agency is lagging on
China imports or on SPR accounting. The model at `trade_thesis.py` has no way to
see divergent agency views. Adding a manual monthly CSV import of IEA headline
stock change and a `eia_iea_divergence_flag: bool` on the context would cost
effectively nothing and stop the LLM from over-weighting a single source.

### 9. [MEDIUM] Cushing 4w slope is the only Cushing signal

`thesis_context.py:154-165` computes `cushing_current_bbls` and
`cushing_4w_slope_bbls_per_day`, both good additions. But **Cushing utilization
as a % of working capacity** (~98 Mbbl shell, ~76 Mbbl operable) is the actual
regime variable — below 30% fill the spread prices "tank bottoms," above 80%
fill it prices "tops-out." A hard-coded `CUSHING_WORKING_CAPACITY_BBLS = 76e6`
constant and a `cushing_utilization_pct` field would give the LLM a regime tag it
cannot derive from slope alone. Two new lines in `thesis_context.py:154`.

### 10. [MEDIUM] CFTC signal is positioning-only, no combined commercial hedging view

`providers/_cftc.py:107-148` extracts producer, swap, managed-money, other-reportable,
and non-reportable nets, and `thesis_context.py:167-188` surfaces MM net, producer
net, and swap net independently. What's missing is the **commercial combined**
(producer + swap) view — producers short-hedge forward production, swap dealers
mirror them on the opposite side for bank flow. A rising **combined short** from
commercials with a **flat MM** is the classic "producers locking in price into a
backwardated curve" signal — historically bullish spot WTI relative to Brent.
Compute `commercial_combined_net = producer_net + swap_net` and expose it at
`thesis_context.py:171` — one line.

### 11. [LOW] Crude tanker cargo heuristic is aggressive

`providers/_aisstream.py:96` hard-codes `Cargo_Volume_bbls = 1_400_000` for every
live vessel. That's ~1 VLCC-equivalent, but the AIS fleet includes Aframaxes
(~700k bbl), Suezmaxes (~1 Mbbl), VLCCs (~2 Mbbl), and ULCCs. Without DWT/load-line
data the heuristic overstates Aframax-dominated regions (North Sea, US Gulf domestic)
and understates VLCC-dominated ones (AG, Caribe). The comment at line 96 flags this
as provisional, but no issue or follow-up exists. When tonnage feeds the sanctioned-
flow indicator (finding 5), this bias compounds.

### 12. [LOW] Intraday pricing exists but intraday spread-vol does not feed the thesis

`data_ingestion.py:50-52` exposes 1-minute Brent/WTI bars. The thesis context
(`thesis_context.py:144-149`) computes 30-day realised vol on daily closes only.
An intraday-realised spread vol (Yang-Zhang or Parkinson on 5-min bars) would
surface when **intraday risk has decoupled from daily vol** — a condition that
precedes weekend-gap risk at Sunday open. The data is already fetched, it just
isn't used.

---

## What I would ship first

If I had one sprint:
1. **Add `WGTSTUS1` + `WDISTUS1` to `providers/_eia.py:37`** and two prompt fields.
2. **Fill `fleet_delta_vs_30d_mbbl` at `thesis_context.py:227`** — the schema is
   already there; the wiring isn't.
3. **Add a Baltic TD3/TD20 TCE scalar** via a once-weekly CSV or a scraped
   Clarksons page — one field, enormous information gain.

Do those three and the LLM stops treating Brent-WTI as a z-score and starts
treating it as a barrel. Everything else on this list is additive margin.
