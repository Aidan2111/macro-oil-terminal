# 08 — Data Engineer review (Phase A)

**Reviewer:** Senior data engineer, ingestion / pipelines lens
**Scope:** `data_ingestion.py`, `providers/*.py`, `thesis_context.py`, and the JSONL audit logs (`data/trade_theses.jsonl`, `data/trade_executions.jsonl`).
**Date:** 2026-04-22
**Method:** static read of the ingestion surface. No live-run profiling.

## Executive summary

The provider layer is well-shaped — clean `fetch_* → Result(frame, source, source_url, fetched_at)` contracts, a single orchestrator per domain, no silent synthetic fallback. What is missing is the *boring* half of data engineering: timezone discipline, stale-data detection, calendar awareness (EIA holidays, NYMEX DST), corporate-action handling for the USO/BNO ETF path that is *advertised* but never ingested, idempotent audit writes, and explicit freshness SLAs. Findings severity-ranked below.

---

## Findings

### F1 — CRITICAL — `fetched_at` is timezone-naive across every provider

Every `Result` dataclass stamps `fetched_at=pd.Timestamp.utcnow()`, which returns a **naive** `Timestamp` in UTC-wallclock — not a tz-aware UTC stamp. Occurrences: `providers/pricing.py:44`, `providers/pricing.py:56`, `providers/pricing.py:68`, `providers/pricing.py:88`, `providers/inventory.py:58`, `providers/_cftc.py:200`, `data_ingestion.py:175`, `data_ingestion.py:188`, `data_ingestion.py:196`. `providers/_yfinance.py:21` and `providers/_polygon.py:44` additionally call `datetime.utcnow()` (deprecated in Py 3.12+). Downstream, `thesis_context.py:191` does `pd.Timestamp.utcnow().tz_localize(None)` — this will throw once pandas tightens `utcnow()` semantics. Fix: `pd.Timestamp.now(tz="UTC")` everywhere; render with `.tz_convert("US/Eastern")` at the UI edge so desks read ET without layer confusion.

### F2 — CRITICAL — No stale-data detection on any feed

Nothing checks that the most-recent bar is actually recent. `providers/_yfinance.py:45-52` reindexes to a full daily `date_range` and `ffill().bfill()` — if yfinance stops updating Friday, reindex + ffill manufactures a "today" row and the dashboard renders stale levels as today's. Same pattern bites `_eia.py:229-231` (ffill on Commercial/SPR/Cushing across EIA holiday skips). No `age_minutes` on any Result, no staleness threshold, no user-visible warning. Fix: (a) compute `age = now - frame.index[-1]` per fetcher, raise or badge above an SLA (24h daily, 30min intraday, 10d weekly EIA); (b) drop the `bfill()` at `_yfinance.py:48` — it can paint historical NaN bars with future values.

### F3 — HIGH — EIA release countdown is wrong 8 months a year (DST not handled)

`thesis_context.py:80-84` computes the next EIA weekly release as 14:30 UTC Wednesday. EIA actually publishes at 10:30 America/New_York: that maps to 14:30 UTC during EST and 15:30 UTC during EDT. The code bakes in the EST value year-round — the comment at `thesis_context.py:70-73` even admits DST is not accounted for. The countdown is therefore 60 minutes off for roughly 8 months. Fix: use `zoneinfo.ZoneInfo("America/New_York")` and convert. Same class of bug implicit in `_cftc.py` — the Friday-15:30-ET COT release is never modeled, so "CFTC is stale" detection cannot exist.

### F4 — HIGH — NYMEX session model ignores Sunday re-open, holidays, and DST

`thesis_context.py:194-199` decides `session_is_open` from UTC hour/DOW alone: `weekend = dow in (5,) or (dow == 6 and hour < 23) or (dow == 4 and hour >= 21)`. This (a) never flips `session_is_open=False` on US federal holidays (Thanksgiving, Christmas, New Year's, Good Friday — all of which close CME crude), so the dashboard greenlights "trade now" on a closed market; (b) hard-codes 21:00 UTC Friday / 23:00 UTC Sunday cutoffs — a DST-dependent mapping to the real 17:00/18:00 ET CME boundary, wrong by one hour in EDT; (c) encodes the ~2-day weekend as a single boolean, erasing the Sunday 18:00 ET re-open window. Use `pandas_market_calendars` or `exchange_calendars` keyed to `CMES`.

### F5 — HIGH — USO/BNO are advertised as a Tier-2 leg but never ingested

The thesis decorator surfaces a USO/BNO ETF pair leg (`trade_thesis.py:335`, `app.py:1072`), the hero renders it (`tests/unit/test_theme_hero.py:92-108`), and the backtest UI references it — but **no provider fetches USO or BNO**. `providers/_yfinance.py:25` only downloads `BZ=F, CL=F`; no corresponding path in `_twelvedata.py` or `_polygon.py`. Consequences: (a) the ETF leg cannot be backtested on real prices; (b) corporate actions on USO (two reverse splits since 2020: 1-for-8 in April 2020 and the December 2020 1-for-4) and BNO distributions are unadjusted because there is nothing to adjust. If ETF pricing is added, note `_yfinance.fetch_daily` at line 29 passes `auto_adjust=False` — fine for futures, broken for USO/BNO across split dates. Action: (i) remove the ETF leg until a provider exists, or (ii) add `_yfinance.fetch_etf(["USO","BNO"])` with `auto_adjust=True`.

### F6 — HIGH — CFTC cache: current-year zip is a moving target

`providers/_cftc.py:170-203` caches parsed year-frames for 24h (`_TTL_SECONDS = 86_400` at line 63) keyed on the sorted tuple of years. The current-year zip (`fut_disagg_txt_2026.zip`) is *rewritten* every Friday — year-to-date, not append-only. The 24h TTL means up to 24h of stale positioning straddling a regulatory event (report publishes ~15:30 ET Friday; if a user warmed cache at 14:00 ET Friday, they see last week's MM net until Saturday 14:00 ET). Second, the cache is in-process only (`_CACHE` at line 62) — every Streamlit rerun in a fresh worker re-downloads the 2024/2025/2026 zips. Fix: cache-key should include `pd.Timestamp.utcnow().date().isoformat()` modulo the Friday release, and persist to `data/.cache/cftc_*.parquet`.

### F7 — HIGH — Audit log appends are not atomic, not deduped, race on multi-worker

`trade_thesis.py:725` writes `data/trade_theses.jsonl` with plain `with _AUDIT_PATH.open("a") as f: f.write(...)` at line 740; `app.py:721-740` mirrors for `data/trade_executions.jsonl`. Issues: (a) multi-worker Streamlit (Gunicorn, multi-instance Cloud Run) will interleave writes — POSIX `O_APPEND` gives atomicity only up to `PIPE_BUF` (4096 bytes); a thesis record with full `ctx.to_dict()` routinely exceeds that and can tear. (b) No dedup on `context_fingerprint` — the same thesis is logged multiple times per minute on refreshes. (c) No rotation. (d) The `except Exception: pass` at `trade_thesis.py:741` and `app.py:741` swallows every error, so broken logging cannot be alerted on. Fix: `fcntl.flock(LOCK_EX)` around the write, or move to SQLite WAL.

### F8 — MEDIUM — `ffill()` across gaps erases data-quality signal

`providers/_eia.py:229-231` ffills SPR, Commercial, and Cushing; `providers/_yfinance.py:48` does `df.reindex(full_idx).ffill().bfill()`. When a publisher misses a day or week the dashboard shows a flat line instead of a gap — the user cannot distinguish "EIA skipped the holiday week" from "inventory is flat WoW." Two concrete harms: (i) `thesis_context.py:125-126` computes `_linear_slope_per_day(inv.tail(4))` — 4 ffilled rows produce slope≈0 and the "days of supply" guardrail at `thesis_context.py:130-132` reads normal; (ii) vol estimation at `thesis_context.py:43-50` on ffilled prices understates realized vol because log-returns across ffilled bars are exactly zero. Keep raw frames; expose a `missing_mask`; ffill only at the plotting layer.

### F9 — MEDIUM — No per-row provenance; single timestamp per fetch

`PricingResult` (`providers/pricing.py:26-33`), `InventoryResult` (`providers/inventory.py:25-31`), and `COTResult` (`data_ingestion.py:208-216`) carry one `source` and one `fetched_at`. `_eia.fetch_inventory` at `_eia.py:206-242` silently falls back v2→dnav at `_eia.py:174-181`, and the Result never records which series came from which path. Add per-series provenance (e.g. `Cushing_bbls_source="EIA-v2"`, `SPR_bbls_source="EIA-dnav"`) so downstream consumers and the audit log can reproduce what was seen.

### F10 — MEDIUM — aisstream.io snapshot uses heuristic cargo volumes, drops position timestamps

`providers/_aisstream.py:96` hard-codes `"Cargo_Volume_bbls": 1_400_000` for every vessel — labeled as a heuristic but ends up in the summed "shadow/sanctioned barrels" at `thesis_context.py:138-141`. Real DWT is in the AIS static data payload; a 10× miss on cargo is not impossible and the number on-screen is load-bearing. Additionally the position `ts` at line 83 (aisstream.io `time_utc`) is dropped — only lat/lon survive. Every vessel is painted "live now" even if the last fix is 3h old. Add (a) DWT→barrels conversion from ship static data (IMO type 5), (b) per-row `position_age_minutes`, (c) filter out fixes > 6h before summing cargo.

### F11 — MEDIUM — Currency assumption "everything is USD" is unverified

Twelve Data symbols `BRN/USD, WTI/USD` at `providers/_twelvedata.py:59-60` look fine, but Twelve Data occasionally returns non-quote currency on ambiguous symbols. Polygon tickers `C:BRN1!, C:WTI1!` at `providers/_polygon.py:43` are not verified USD-denominated (some Polygon Brent feeds settle in GBP). yfinance `BZ=F, CL=F` at `providers/_yfinance.py:25` are USD by contract spec — fine. EIA and FRED are unit-labeled (barrels) — OK. CFTC reports contract counts — OK. Action: add `currency: str = "USD"` to `PricingResult` and reject any response whose metadata contradicts.

### F12 — LOW — Intraday alignment drops rows silently

`providers/_yfinance.py:78` calls `df.dropna(how="any")` to align Brent/WTI 1-min bars. A 3-minute stall on one side (common at the ICE re-open) silently discards 3 minutes. No log, no warning. Vol computation at `thesis_context.py:144-150` treats the remaining bars as contiguous, inflating realized vol because a 3-minute gap now looks like a 1-minute jump. Emit a `dropped_bars` counter; consider `dropna(how="all")` + ffill for display only.

### F13 — LOW — CFTC `market_name` can be blank

`providers/_cftc.py:180-181` and `:201-202` fall back to `""` when cached frame is empty. `_compute_net_positions` at line 129 unconditionally sets `market: r.get("_matched_market", "")` — if the first accepted name in `_ACCEPTED_MARKET_NAMES` at line 50-54 ever shifts, rows with blank markets slip through and `cftc_res.market_name` is `""`. The UI cites source by market name. Assert non-empty at the boundary.

---

## Recommended Phase B actions

1. Adopt `pd.Timestamp.now(tz="UTC")` across providers; `.tz_convert("US/Eastern")` at the UI edge.
2. Add `age_minutes` / `max_age_minutes_sla` to every `*Result`; raise-or-badge on breach.
3. Swap `_next_wednesday` for `pandas_market_calendars("CMES")` + `zoneinfo`.
4. Decide USO/BNO: ingest with `auto_adjust=True`, or delete the Tier-2 ETF leg.
5. Replace JSONL audit appends with SQLite (WAL) or `fcntl.flock`; add rotation.
6. Persist the CFTC and EIA-v2 in-process caches to `data/.cache/*.parquet`.
7. Remove `.bfill()` from `_yfinance.fetch_daily`; tag missing rows instead.
8. Add per-series provenance columns to `InventoryResult.frame` and `PricingResult.frame`.

Phase A (read-only) is complete.
