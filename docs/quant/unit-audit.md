# Provider unit-label audit — issue #96

Sweep of every numeric field served by `/api/*` against the unit the
underlying provider publishes. The audit was triggered by issue #91
(STEO `COPR_IR` mislabelled as kbpd when EIA publishes it in MMbbl/d);
this doc is the systematic version of that one-off fix.

## Audit methodology

For each field:

1. The provider's source-of-truth unit is identified from upstream
   docs (EIA series catalogue, CFTC dictionary, AISStream schema,
   yfinance endpoint contract).
2. The field name and emitted value are inspected on a live
   `/api/*` response.
3. The conversion path (provider → service → response) is traced and
   commented inline in the code.
4. Any mismatch is fixed at the **provider** boundary so downstream
   consumers can trust the field name.

## Field-by-field table

| Endpoint | Field | Native unit | Emitted unit | Status | Verification |
|---|---|---|---|---|---|
| `/api/spread` | `brent`, `wti` | USD/bbl | USD/bbl | OK | yfinance `BZ=F` / `CL=F` close in $/bbl |
| `/api/spread` | `spread` | USD/bbl | USD/bbl | OK | Brent − WTI difference, $/bbl |
| `/api/spread` | `stretch`, `z_score` | unitless σ | unitless σ | OK | Z-score of spread/std |
| `/api/spread` | `history[].brent / wti / spread` | USD/bbl | USD/bbl | OK | Same as above |
| `/api/inventory` | `commercial_bbls`, `spr_bbls`, `cushing_bbls`, `total_bbls` | EIA kbbl | bbl (×1000 at provider) | OK | `providers/_eia.py:95,168` apply `* 1000.0` |
| `/api/inventory/history[]` | per-week bbl fields | EIA kbbl | bbl (×1000) | OK | Same conversion, same source |
| `/api/cftc` | `mm_net`, `commercial_net`, `producer_net`, `swap_net` | CFTC contracts (1k bbl ea.) | contracts | OK | CFTC disaggregated reports — units = contracts; UI must scale by 1000 bbl/contract for notional |
| `/api/cftc` | `mm_zscore_3y` | unitless σ | unitless σ | OK | Z-score |
| `/api/cftc` | `open_interest` | contracts | contracts | OK | CFTC field |
| `/api/inventory/iran-production` | `latest_kbpd`, `ytd_avg_kbpd`, `delta_vs_ytd_avg_kbpd` | EIA STEO MMbbl/d | kbbl/d (×1000 at provider) | **FIXED in this PR** | EIA STEO `COPR_IR` documentation; multiplier added to `_STEO_UNIT_MULTIPLIERS` |
| `/api/inventory/iran-production` | `monthly[].kbpd` | EIA STEO MMbbl/d | kbbl/d (×1000) | **FIXED in this PR** | Same — provider boundary applies multiplier |
| `/api/geopolitical/hormuz` | `transits_24h`, `transits_pct_1y` | vessel count, % | count, % | OK | AIS-derived counts; `pct_1y` is a unitless ratio |
| `/api/geopolitical/russia` | `chokepoint_transits_24h`, `chokepoint_transits_pct_1y` | vessel count, % | count, % | OK | Same as Hormuz |
| `/api/fleet/iran` | `export_tankers_7d`, `import_tankers_7d` | vessel count | count | OK | Tanker-day counter |
| `/api/fleet/snapshot` | `vessels[].Cargo_Volume_bbls` | bbl | bbl | OK | AIS DWT-to-cargo lookup; ~1.4M bbl per VLCC checks out |
| `/api/fleet/snapshot` | `vessels[].Latitude / Longitude` | decimal degrees | decimal degrees | OK | AIS standard |
| `/api/news/headlines` | `recent_headlines[].vader_score` | [-1, 1] | [-1, 1] | OK | VADER compound score range |
| `/api/sanctions/delta` | `new_sanctions_iran_30d`, `new_sanctions_russia_30d`, `new_sanctions_venezuela_30d` | count of new SDN entries | count | OK | OFAC SDN delta |
| `/api/track-record` | `sharpe`, `sortino`, `calmar` | unitless ratio | unitless ratio | OK | Annualised return / std |
| `/api/track-record` | `var_95`, `es_95`, `es_975` | USD per trade | USD per trade | OK | Per-trade PnL distribution percentile (issue #64) |
| `/api/track-record` | `max_drawdown_usd`, `total_pnl_usd` | USD | USD | OK | Cumulative PnL |
| `/api/track-record` | `hit_rate`, `win_rate` | proportion [0, 1] | proportion | OK | Wins / total |
| `/api/backtest` | `metric_cis[*]` | same as point estimate | same as point estimate | OK | Issue #94 — bootstrap CI on each metric |
| `/api/data-quality` | `last_good_at` | ISO-8601 UTC | ISO-8601 UTC | OK | Always ISO timestamp |
| `/api/data-quality` | `n_obs`, `latency_ms` | count, milliseconds | count, ms | OK | Provider envelope |

## Mismatches found and fixed in this PR

### `COPR_IR` STEO series — MMbbl/d → kbbl/d (closes #91)

`providers/_eia.py::fetch_steo_series` previously returned EIA STEO
values verbatim. EIA publishes `COPR_IR` (Iran crude production),
`COPR_RU` (Russia), and `COPR_VE` (Venezuela) in MMbbl/d. The
downstream service named the field `latest_kbpd` but actually held
~3.3 (an MMbbl/d value).

Fix: a per-series multiplier map (`_STEO_UNIT_MULTIPLIERS`) at the
provider boundary. `COPR_IR`, `COPR_RU`, and `COPR_VE` are tagged with
a `1000.0` conversion. `latest_kbpd` now holds ~3300 — the correct
kbbl/d figure. New regression tests
(`test_steo_unit_multiplier_converts_mmbpd_to_kbpd_for_copr_ir`,
`test_iran_production_envelope_in_kbpd_after_provider_conversion`)
lock the conversion in.

## No mismatches found

Every other endpoint listed above is internally consistent — the
provider unit, the conversion (if any), and the field name agree.
Inventory `_bbls` fields look surprisingly large (e.g.
`commercial_bbls=459_495_000`) but that is the genuine 459M bbl
commercial-stocks figure: EIA publishes 459,495 thousand bbl, and the
provider multiplies by 1000 to land in raw barrels.

## Onboarding checklist for new providers

When adding a new numeric field to any `/api/*` response:

1. Document the source-of-truth unit in the provider docstring.
2. If the source unit differs from the canonical we serve, apply the
   conversion **at the provider boundary** (not the service layer or
   the route).
3. Pick a field name that names the canonical unit (`_bbls`,
   `_kbpd`, `_usd`, `_pct`).
4. Add a row to the table above.
5. Add a regression test asserting the value lies in a plausible band
   for that unit (not ~3.3 for kbpd, etc.).
