# Persona 10 — Performance engineer review (Phase A)

Lens: latency, scalability, memory, cold-start. Files read: `app.py`,
`theme.py`, `data_ingestion.py`, `providers/*.py`, `quantitative_models.py`,
`.github/workflows/keep-warm.yml`, `docs/perf/ui_polish_deltas.md`. T10
numbers (58s baseline cold, 1.6s polished cold) are treated as the
ground-truth perf envelope; everything below either explains those
numbers or calls out what still leaks inside them.

Findings are ranked by severity (S1 = blocker for the stated budget,
S4 = cosmetic). Every finding cites file+line.

---

## S1-a — Walk-forward + Monte Carlo backtests run inline, not cached, inside an `st.expander`

`app.py:1519-1616`: opening the "Walk-forward, Monte Carlo, regime
breakdown" expander in Tab 1 fires three *uncached* quant passes on every
rerender:

- `walk_forward_backtest(...)` at `app.py:1529` — re-runs
  `backtest_zscore_meanreversion` on overlapping 12-month slices stepping
  every 3 months (`quantitative_models.py:452-475`). On ~5y of daily
  data that is ~17 slices × the full per-bar Python loop at
  `quantitative_models.py:301-331`.
- `monte_carlo_entry_noise(...)` at `app.py:1566`, **200 runs** of the
  full backtest with perturbed `entry_z` (`quantitative_models.py:
  500-511`). This is by far the heaviest code path in the app —
  O(200 × N_bars) Python-level iteration.
- `regime_breakdown(...)` at `app.py:1589`.

None of these are wrapped in `@st.cache_data`, while the *simple*
backtest right above them IS cached (`app.py:379-388`). Every slider
tweak (`z_threshold`, `slippage_per_bbl`) triggers a full Streamlit
rerun; if the expander is left open, it pays the MC cost on every tick.
On a cold, small-SKU Azure instance this is the single largest driver
of the ~22s warm hero-visible number in
`docs/perf/ui_polish_deltas.md:24`.

**Fix:** wrap all three helpers in `@st.cache_data` keyed on
`(_fp(spread_df), entry_z, exit_z, slippage, commission)`; or gate the
whole expander body behind an `st.session_state` "user opened it"
latch so first render doesn't pay the cost. Either move alone should
bring warm TTI under 2s on canadaeast.

## S1-b — `canadaeast` cold-start is dominated by Python import surface, not network

`docs/perf/ui_polish_deltas.md:22-25` shows 58s baseline cold → 1.6s
polished cold, but the polished number is local loopback; the warm
canadaeast path is still 22s (`ibid:24`). Root cause is the import
graph at `app.py:19-85`: Streamlit pulls `pandas`, `plotly.graph_objects`,
`plotly.subplots`, then transitively `sklearn.linear_model`
(`quantitative_models.py:18`), `statsmodels` via `cointegration.engle_granger`
(imported eagerly at `app.py:50`), `yfinance`, `websockets`. A cold
worker on a B1 / F1 App Service SKU spends 10-15s just importing
sklearn + statsmodels before the first `st.markdown` executes.

**Fix options, ordered by ROI:** (1) move `sklearn`, `statsmodels`,
`webgpu_components` to lazy imports inside the functions that use them
(`forecast_depletion`, `engle_granger`, `render_hero_banner`); (2) bump
the App Service SKU one tier — canadaeast B1 in particular has a cold
JIT that's noticeably slower than westus2 B1; (3) precompile `.pyc`
at container build and set `PYTHONDONTWRITEBYTECODE=0` so the warm path
doesn't pay compile cost per-worker.

## S1-c — `_backtest_cached` fingerprint drops the slider that can invalidate the result

`app.py:379-388`: the cache key is
`(spread_fingerprint, entry_z, exit_z, slippage, commission)`. But the
`spread_fingerprint` is built from `_fp(spread_df)` (`app.py:428-429`)
as `f"{len(df)}-{df.index[-1]}"`. Two distinct 5y frames with the same
last date and same length collapse to the same key — e.g. after a
`yfinance` retry that back-fills a single missing bar, the cache hits
on a stale trade blotter. Same problem on
`_spread_cached` / `_depletion_cached` / `_cointegration_cached`
/ `_crack_cached` (`app.py:369-426`). This is a correctness-leaning
perf bug: the *next* stale hit after a data refresh ships the wrong
Sharpe number to the hero band because `bt` feeds
`thesis_context.build_context` at `app.py:1111`.

**Fix:** fingerprint with a cheap content hash, e.g.
`hashlib.md5(pd.util.hash_pandas_object(df).values).hexdigest()` or
just `str(df['Brent'].iloc[-1]) + str(len(df))`. Costs one more column
read — negligible relative to the rest of the compute.

## S2-a — `@st.fragment(run_every=60)` ticker: no backpressure, no failure budget

`app.py:478-552`: the ticker fragment fires every 60s and pulls
`_load_intraday_cached(bucket)` which is a `ttl=45s` cache
(`app.py:457-463`). Under a slow / flapping yfinance the inner
`yf.Ticker(...).history(period="2d", interval="1m")`
(`providers/_yfinance.py:65-66`) can block for 10+s twice per minute
(once each for BZ=F and CL=F, serial — no `asyncio.gather`, no
`threads=True`). If the fragment's previous tick is still blocked when
the next one fires, Streamlit serializes them; on a free SKU this
starves the main thread and the tab-switch latency balloons.

**Fix:** (a) parallelise the two tickers (`concurrent.futures`); (b) set
a hard 5s timeout on the yfinance call and fall back to the daily tail
(which is already the `else` branch at `app.py:493-495` — just surface
the timeout to that path); (c) widen the cache TTL to match the
fragment period (45s → 60s) so the bucket-aligned key
`_load_intraday_cached(bucket)` doesn't churn.

## S2-b — aisstream websocket has no backpressure or dedupe on reconnects

`providers/_aisstream.py:31-103`: `_collect_snapshot` opens a websocket,
reads for `seconds` (default 20 — `providers/_aisstream.py:124`), and
stuffs every PositionReport into `records[mmsi]`. There's no cap on
message rate, no skip-if-behind logic, and the outer
`@st.cache_data(ttl=30min)` (`app.py:294-296`) means the 20s block
happens on the main render thread every half-hour. During the block,
first-paint on any rerun that hits `_load_ais_cached()` stalls for up
to 20s.

**Fix:** move the websocket collector to a background thread with a
shared buffer (`threading.Lock`), and have `fetch_ais_data` return
whatever the buffer holds (falling back to the historical snapshot if
the buffer is empty). This is also an S3 memory point: the in-flight
`records` dict is unbounded between reconnects.

## S2-c — Hero thesis LLM call fires inside the render pass

`app.py:1122-1128`: if `_thesis_obj` is absent from session_state,
`_gen_thesis(_hero_ctx, mode="fast")` runs synchronously before
`_render_hero_band` is called. A gpt-4o fast call is ~2s on a good day
and 5-10s when Azure OpenAI is slow. That full latency ladders into
the first-paint budget for every first-session user — exactly the
population that's most likely to bounce. The T10 local-loopback
number of 1.6s in `docs/perf/ui_polish_deltas.md:22` does not include
this because the measurement doesn't exercise Azure OpenAI.

**Fix:** render a placeholder hero (the `thesis is None` branch at
`app.py:1008-1025` already exists), then kick the LLM call off a
background thread and re-render via `st.rerun()`. Budget target:
first-paint hero-visible should not depend on any external API call.

## S2-d — Plotly main-chart uses `Scattergl` but re-creates the figure every rerun

`app.py:1276-1348`: the Tab-1 spread chart builds a fresh `make_subplots`
+ three `Scattergl` traces on every rerun, including slider-driven
reruns. `Scattergl` is the right trace type (we want WebGL on 5y of
daily bars), but the figure itself isn't memoized. A slider tweak that
only needs to redraw the `+z_threshold` horizontal line pays a full
figure rebuild + JSON serialization through the streamlit-plotly
bridge.

**Fix:** either cache the base figure (no threshold lines) with
`@st.cache_resource` keyed on `_fp(spread_df)`, mutate `hline`s via
`fig.update_layout(shapes=...)` on the cached figure, or wrap the
whole chart block in its own `st.fragment` so slider reruns don't
rerun the upstream backtest compute that also fires on the same page.

## S3-a — CSS injection is already once-per-session — but a second `<style>` block is emitted right after

`theme.py:326-372` assembles one ~2KB `<style>` blob and guards on
`st.session_state["_theme_css_injected"]` so it only writes once. Good.
Then `app.py:134-146` *unconditionally* writes a second `<style>`
block (`.block-container`, `.stTabs`, `.big-metric`) plus two
`<link rel="preconnect">` tags. That second block runs on every rerun
(no guard). It's small (~300B) but it defeats the "single injection"
property that `theme.inject_css` advertises at `theme.py:348-373`, and
it duplicates `.block-container { padding-top: ... }` rules that
`_CSS_SPACING` at `theme.py:83-86` already declares.

**Fix:** fold the three rules into `theme._CSS_SPACING` and the
preconnect `<link>`s into the single-injection path. Saves nothing
measurable per-render, but it removes a contributor to "why does
first-paint vary 100ms run-to-run".

## S3-b — Onboarding iframe always mounts, even on repeat visits

`theme.py:1370-1397`: `render_onboarding()` calls
`st.components.v1.html(body, height=1)` every render. The JS inside
correctly short-circuits on `localStorage["mot_onboarding_done"]`
(`theme.py:1222-1227`), but the iframe itself — ~4KB of inline CSS+JS —
still posts back to Streamlit's components endpoint on every rerun.
On a slow mobile link this is an extra 20-40ms round-trip per render.

**Fix:** guard at the Python side on a session_state flag set by a
one-shot `st.query_params` rewrite after the JS sets the localStorage
key, or accept that 1-of-N renders on first visit mount the iframe
and skip it thereafter by wrapping `render_onboarding()` in a
`st.session_state.get("_onboarding_shown")` check.

## S3-c — Rolling buffer memory: spread_df and intraday both held full-history in memory

`app.py:432` materialises the full 5y `spread_df` (1800+ daily bars ×
8 float columns after `compute_spread_zscore` at
`quantitative_models.py:46-67`). Cheap on its own. But
`_load_intraday_cached` at `app.py:457-463` holds `period="2d"` of
1-min bars (~780 rows × 2 cols), and the ticker fragment at
`app.py:511` computes `(brent_tail - wti_tail).dropna().tail(120)`
on every tick without slicing the series first — the subtraction
broadcasts across the full 2-day frame and then tails. At 60s cadence
× N concurrent sessions, this is measurable on a B1.

**Fix:** `brent_tail.tail(120)` and `wti_tail.tail(120)` *before* the
subtraction at `app.py:511`. Microscopic win per call; compounds on
a keep-warm schedule that fires every 10 minutes
(`.github/workflows/keep-warm.yml:6`).

## S4-a — Keep-warm workflow is too aggressive for the budget it's protecting

`.github/workflows/keep-warm.yml:5-8`: every 10 min 07:00-22:00 UTC,
every 30 min overnight. That's ~112 pings/day against
`/_stcore/health`. On a B1 canadaeast instance this is enough to keep
the CPU above idle but not enough to keep the Python workers warm —
the Streamlit session dies after ~15 min of inactivity regardless of
health pings (the health endpoint doesn't boot a session). So this
workflow pays CI minutes without actually warming the path that
matters (the first `streamlit run` render).

**Fix:** either (a) hit a real page path (`/` with a `?warm=1` query
so it isn't billed toward real-user metrics) to force a full session
boot, or (b) drop the overnight schedule entirely — 30-min pings to
a health endpoint that doesn't warm sessions buys nothing.

## S4-b — Mobile CPU profile: inline SVG sparkline rebuilds every tick, 4 traces

`theme.py:678-761`: `_build_sparkline_polyline` runs 4 times per
ticker tick (one per quote dict in `app.py:517-551`), each doing a
Python-level min/max + string format over 50-120 floats. Per tick
this is <1ms — not a real bottleneck — but on a slow phone the outer
`st.markdown(...)` innerHTML replace forces a full style recalc on
the ticker strip container. Worth noting because the T10 deltas doc
at `docs/perf/ui_polish_deltas.md:40-47` specifically calls out
"warm path over budget" and the ticker fragment is the most
frequently-redrawn element on the page.

**Fix:** diff against the previous tick's quote dict (`st.session_state`)
and skip the `st.markdown` write when nothing changed. Also consider
fragment-scoping the strip render (already done at `app.py:478`) so
the outer page CSS doesn't re-invalidate.

---

## Summary budget math

| Source | Cold (canadaeast) | Warm (canadaeast) |
|---|---|---|
| Python imports (sklearn, statsmodels, plotly) | ~12s | — |
| yfinance daily + inventory fetch | ~4s (cache miss) | 0 (hit) |
| LLM `_gen_thesis` fast-path | ~2-5s | 0 (session_state hit) |
| Uncached WF+MC+regime if expander open | — | 8-15s |
| Plotly figure rebuild per rerun | — | ~300ms |
| CSS injection | ~2KB, once | 0 |
| **Measured (T10)** | 58s baseline → 1.6s polished local | 22s canadaeast / 4.7s local |
| **Target** | ≤4s | ≤2s |

Closing the warm gap to ≤2s needs **S1-a + S2-c** shipped together
(the MC loop and the LLM-in-render are the two biggest warm-path
leaks). Closing the cold gap on canadaeast needs **S1-b** (lazy
imports) + real-page keep-warm (S4-a). Everything else is
correctness hardening that pays small individual wins.
