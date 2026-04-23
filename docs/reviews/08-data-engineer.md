# 08 — Data Engineer review (Phase A)

**Reviewer:** Senior data engineer, ingestion / pipelines lens
**Scope:** `data_ingestion.py`, `providers/*.py`, `thesis_context.py`, and the JSONL audit logs (`data/trade_theses.jsonl`, `data/trade_executions.jsonl`).
**Date:** 2026-04-22
**Method:** static read of the ingestion surface. No live-run profiling.

## Executive summary

The provider layer is well-shaped — a clean `fetch_* → Result(frame, source, source_url, fetched_at)` contract, a single orchestrator per domain, and no silent synthetic fallback in the production path. The fingerprint of a real, credible terminal is there. What is missing is the *boring* half of data engineering: timezone discipline, stale-data detection, calendar awareness (EIA holidays, NYMEX DST), corporate-action handling for the USO/BNO ETF path that is *advertised* to users but not actually ingested, idempotent audit writes, and an explicit freshness SLA. The list below is ranked by severity.

---

## Findings

### F1 — CRITICAL — `fetched_at` is timezone-naive across every provider; UI timestamps are ambiguous

Every `Result` dataclass stamps `fetched_at=pd.Timestamp.utcnow()` which as of pandas ≥ 2.0 returns a **naive** `Timestamp` in UTC-wallclock — *not* a tz-aware UTC stamp. Occurrences: `providers/pricing.py:44`, `providers/pricing.py:56`, `providers/pricing.py:68`, `providers/pricing.py:88`, `providers/inventory.py:58`, `providers/_cftc.py:200`, `data_ingestion.py:175`, `data_ingestion.py:188`, `data_ingestion.py:196`. `providers/_yfinance.py:21` and `providers/_polygon.py:44` additionally call `datetime.utcnow()` (deprecated in Py 3.12+, slated for removal). Downstream, `thesis_context.py:191` does `pd.Timestamp.utcnow().tz_localize(None)` — which will throw `TypeError: Already tz-naive, use tz_convert to localize` once pandas tightens `utcnow()` semantics. Fix pattern: `pd.Timestamp.now(tz="UTC")` everywhere, and render with `.tz_convert("US/Eastern")` at the UI edge so desks read ET without the layer confusion.

### F2 — CRITICAL — No stale-data detection on any feed

Nothing in the provider layer checks that the most-recent bar/row is actually recent. `providers/_yfinance.py:45-52` reindexes to a full daily `date_range` and `ffill().bfill()` — so if yfinance silently stops updating Friday, the dashboard will cheerfully render stale Brent/WTI levels as though they were today's, because the reindex + ffill manufactures a "today" row. Same pattern would bite `_eia.py:229-231` (`ffill` on commercial / SPR / Cushing — the EIA can and does miss publishing windows around holidays). There is no `age_minutes` field on `PricingResult` / `InventoryResult`, no staleness threshold, and no user-visible warning. Minimum fix: (a) compute `age = now - frame.index[-1]` at the end of each fetcher, attach to the Result, and raise or badge when it exceeds an SLA (24h daily, 30min intraday, 10d weekly for EIA). (b) drop the `bfill()` at `_yfinance.py:48` — it can retroactively paint historical NaN bars with future values, which is worse than a missing row.

### F3 — HIGH — EIA release time is wrong 8 months a year (DST not handled)

`thesis_context.py:80-84` computes the next EIA weekly release as `14:30 UTC Wednesday`. EIA publishes the weekly petroleum status report at **10:30 America/New_York**, which is 14:30 UTC only during EST; during EDT (mid-March → early November) it is **14:30 UTC is wrong — the release is at 14:30 UTC in EST but 14:30 UTC = 10:30 EDT is equivalent to…**. Concretely, 10:30 ET → 15:30 UTC during EDT, 14:30 UTC during EST. The code bakes in the EST value year-round (see comment at `thesis_context.py:70-73` which admits this). The UI-displayed countdown will therefore be 60 minutes off for roughly 8 months of the year. Fix: use `zoneinfo.ZoneInfo("America/New_York")` and convert, rather than hard-coding UTC. Same class of bug implicitly in `_cftc.py` — the Fridays-at-15:30-ET COT release is never modeled, so "CFTC is stale" detection cannot exist.

### F4 — HIGH — NYMEX session model ignores Sunday re-open, holidays, and DST

`thesis_context.py:194-199` decides `session_is_open` from UTC hour/DOW alone: `weekend = dow in (5,) or (dow == 6 and hour < 23) or (dow == 4 and hour >= 21)`. This: (a) never flips `session_is_open=False` on US federal holidays (Thanksgiving, Christmas, New Year's, Good Friday — all of which close CME crude), so the dashboard will greenlight "trade now" on a closed market; (b) hard-codes 21:00 UTC Friday / 23:00 UTC Sunday cutoffs, which is a DST-dependent mapping to the real 17:00/18:00 ET CME boundary — wrong by one hour in EDT; (c) has a *5-hour* implicit gap between "Friday 17:00 ET close" and "Sunday 18:00 ET re-open" encoded as a single boolean, erasing the Sunday night 23:00 UTC — Monday 00:00 UTC re-open window. Use `pandas_market_calendars` or `exchange_calendars` keyed to `CMES` for a real answer.

### F5 — HIGH — USO/BNO are advertised as a Tier-2 trade leg but never ingested

The thesis decorator surfaces a USO/BNO ETF pair leg (`trade_thesis.py:335`, `app.py:1072`), the hero renders it (`tests/unit/test_theme_hero.py:92-108`), and the backtest UI references it — but **no provider fetches USO or BNO**. `providers/_yfinance.py:25` only downloads `BZ=F, CL=F`; no corresponding path exists in `_twelvedata.py` or `_polygon.py`. Consequences: (a) the ETF leg cannot be backtested on real prices; (b) corporate actions on USO (two reverse splits since 2020: 1-for-8 in April 2020 and the December 2020 1-for-4 collapse of USO's maturity ladder) and BNO (distribution history) are not adjusted because there is nothing to adjust. If ETF pricing is added later, note that `_yfinance.fetch_daily` at line 29 passes `auto_adjust=False` — for the futures it does not matter (no splits), but for USO/BNO it absolutely does; you would be pulling un-adjusted prices and computing fictitious returns across the split date. Action: either (i) remove the ETF leg until a provider exists, or (ii) add `_yfinance.fetch_etf(["USO","BNO"])` with `auto_adjust=True` AND document it.

### F6 — HIGH — CFTC cache is keyed by year-set but the current-year zip is a moving target

`providers/_cftc.py:170-203` caches the parsed year-frame for 24h (`_TTL_SECONDS = 86_400` at line 63) keyed on the sorted tuple of years. Two issues: (1) The current-year zip (`fut_disagg_txt_2026.zip`) is *rewritten* every Friday by CFTC — it's year-to-date, not append-only. The 24h TTL means up to 24h of stale positioning the Friday *after* a new report lands (report publishes ~15:30 ET Friday; if a user hit the dashboard at 14:00 ET Friday and repopulated cache, they see last week's MM net until Saturday 14:00 ET). Worst-case straddling a regulatory event window. (2) The cache is in-process only (`_CACHE: dict[...]` at line 62) — any Streamlit rerun that spawns a fresh Python worker re-downloads the full 2024/2025/2026 zips (several MB each). Fix: cache-key should include `pd.Timestamp.utcnow().date().isoformat()` modulo the Friday release boundary, and persist to `data/.cache/cftc_*.parquet` so Streamlit warm-ups are fast.

### F7 — HIGH — Audit log appends are not atomic, not deduped, and race on multi-worker

`trade_thesis.py:725` writes to `data/trade_theses.jsonl` with a plain `with _AUDIT_PATH.open("a") as f: f.write(...)` at line 740; `app.py:721-740` does the same for `data/trade_executions.jsonl`. Issues: (a) multi-worker Streamlit (Gunicorn, or multiple Cloud Run instances) will interleave writes — POSIX `O_APPEND` gives atomicity per-write only up to `PIPE_BUF` (4096 bytes on Linux); a thesis record with full `ctx.to_dict()` routinely exceeds that and can be corrupted. (b) No dedup on `context_fingerprint` — the same thesis can be logged multiple times per minute if the user refreshes. (c) No rotation; the file grows unbounded and silently fails when the volume fills. (d) The `except Exception: pass` at `trade_thesis.py:741` and `app.py:741` swallows every error, so you cannot alert when the log is broken. Minimum fix: use `fcntl.flock(LOCK_EX)` around the write, or move to a SQLite WAL store. At the very least, JSON-Lines guarantees one row per line *only* if writes do not tear.

### F8 — MEDIUM — Inventory and pricing silently `ffill()` across gaps, erasing data-quality signal

`providers/_eia.py:229-231` does `df["SPR_bbls"].ffill()`, same for Commercial and Cushing. `providers/_yfinance.py:48` does `df.reindex(full_idx).ffill().bfill()`. The moment a publisher misses a day or week the dashboard shows a flat line instead of a gap — which means the user cannot distinguish "EIA skipped the holiday week" from "inventory is flat week-over-week." Two concrete harms: (i) `thesis_context.py:125-126` computes `_linear_slope_per_day(inv.tail(4))` — 4 ffilled rows will produce slope≈0 and the guardrail "days of supply" path at `thesis_context.py:130-132` will incorrectly read normal; (ii) vol estimation in `thesis_context.py:43-50` on ffilled prices understates realized vol because log-returns across ffilled bars are exactly zero. Mitigation: keep raw frames; expose a `missing_mask` column the UI can badge. Ffill only at the plotting layer, not the analytics layer.

### F9 — MEDIUM — No provenance on individual rows; only one timestamp per fetch

`PricingResult` (`providers/pricing.py:26-33`), `InventoryResult` (`providers/inventory.py:25-31`), and `COTResult` (`data_ingestion.py:208-216`) carry exactly one `source` string and one `fetched_at`. When the frame is a *concatenation* of providers — as the inventory path contemplates at `providers/inventory.py:46-61` (EIA then FRED) — the Result claims whichever provider "won" first, but the actual `_eia.fetch_inventory` at `_eia.py:206-242` *itself* silently falls back from v2 API to dnav at `_eia.py:174-181`, and the Result never records which path was used for each series. Add a per-series provenance column (e.g. `{"Cushing_bbls_source": "EIA-v2", "SPR_bbls_source": "EIA-dnav"}`) so downstream consumers and the audit log can reproduce what was seen.

### F10 — MEDIUM — aisstream.io snapshot uses heuristic cargo volumes and mixed-timezone timestamps

`providers/_aisstream.py:96` hard-codes `"Cargo_Volume_bbls": 1_400_000` for every vessel — this is labeled as a heuristic but ends up in the summed "shadow/sanctioned barrels" displayed on the dashboard (`thesis_context.py:138-141`). Real DWT from AIS static data is in the message; a 10× miss on cargo is not impossible and the number on-screen is load-bearing. Additionally the AIS position `ts` at line 83 is the aisstream.io `time_utc` (ISO string, UTC) but is dropped — we only keep lat/lon. So every vessel is painted as "live now" even if the last position fix is 3 hours old. Add (a) DWT-to-barrels conversion via ship static data (IMO broadcast type 5), (b) a per-row `position_age_minutes`, and filter out vessels with fixes older than ~6h before summing cargo.

### F11 — MEDIUM — Currency assumption ("everything is USD") is unverified, not enforced

The terminal's numeric spine is USD and nothing in the ingestion layer checks that. Twelve Data symbols `BRN/USD, WTI/USD` at `providers/_twelvedata.py:59-60` look fine, but Twelve Data occasionally returns non-quote currency if the symbol is ambiguous. Polygon crude tickers `C:BRN1!, C:WTI1!` at `providers/_polygon.py:43` — not verified to be USD-denominated (some Polygon crude feeds are GBP-settled Brent). yfinance `BZ=F, CL=F` at `providers/_yfinance.py:25` are USD by contract spec, fine. EIA and FRED are unit-labeled (barrels, not currency) — OK. CFTC reports contract counts, not dollars, and positions are multiplied at the UI layer — OK. Action: add a `currency: str = "USD"` assertion to `PricingResult` and reject any provider response whose metadata contradicts it.

### F12 — LOW — Intraday alignment drops rows silently; no gap accounting

`providers/_yfinance.py:78` calls `df.dropna(how="any")` to align Brent and WTI 1-min bars. If one side stalls for 3 minutes (common on BZ=F during the ICE re-open gap), all 3 minutes are silently discarded. There is no log of how many bars were dropped, no warning surfaced, and the downstream vol calculation in `thesis_context.py:144-150` will treat the remaining bars as contiguous — inflating realized vol because a 3-minute gap now looks like a 1-minute jump. Emit a `dropped_bars` counter on `PricingResult`, and consider `dropna(how="all")` + ffill for display only while keeping the raw frame for analytics.

### F13 — LOW — CFTC cache stores `market_name` from `.iloc[-1]` which can be blank

`providers/_cftc.py:180-181` and `:201-202` both fall back to `""` for `market_name` when the cached frame is empty, but the "empty" check is already done above (raise at line 192). The `.iloc[-1]` on `net["market"]` is safe only because `_compute_net_positions` at line 129 unconditionally includes `"market": r.get("_matched_market", "")`. If the first accepted name in `_ACCEPTED_MARKET_NAMES` at line 50-54 ever shifts, rows with blank markets will slip through and `cftc_res.market_name` will be `""` — and the UI cites source by market name. Assert non-empty at the boundary.

---

## Recommended Phase B actions

1. Adopt `pd.Timestamp.now(tz="UTC")` across providers; add `.to_american_eastern()` helper for the UI.
2. Add `age_minutes` / `max_age_minutes_sla` to every `*Result`; raise-or-badge on breach.
3. Swap the hand-rolled `_next_wednesday` for `pandas_market_calendars("CMES")` + `zoneinfo`.
4. Decide USO/BNO: ingest with `auto_adjust=True`, or delete the Tier-2 ETF leg from the thesis.
5. Replace JSONL audit appends with SQLite (WAL mode) or fcntl-locked writes, add rotation.
6. Persist the CFTC and EIA-v2 in-process caches to `data/.cache/*.parquet`.
7. Remove `.bfill()` from `_yfinance.fetch_daily`; tag missing rows instead of synthesizing them.
8. Add per-series provenance columns to `InventoryResult.frame` and `PricingResult.frame`.

Phase A (read-only) is complete.
