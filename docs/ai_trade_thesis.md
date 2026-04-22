# AI Trade Thesis — prompt, schema, guardrails

The Tab 4 "AI Trade Thesis" card is an LLM-generated trade view grounded
in the terminal's real market state. It is *not* generic commentary —
it's a structured trade plan: stance, entry/target/stop, sizing, and
explicit invalidation conditions, all validated against a JSON schema
before rendering.

## Data flow

```
  EIA inventory  ┐
  yfinance price ├──►  thesis_context.build_context()  ──► ThesisContext (dict)
  backtest stats │
  fleet agg      │                                            │
  vol + calendar ┘                                            ▼
                                                JSON payload + system prompt
                                                             │
                                             Azure OpenAI (json_schema)
                                                             │
                                                  raw dict (validated)
                                                             │
                                              _apply_guardrails()
                                                             │
                                                      Thesis object
                                                             │
                                                 render + audit JSONL
```

## System prompt

```text
You are a senior commodities trading analyst specialising in the Brent-WTI
spread and physical crude flows. You produce rigorous trade theses grounded
ONLY in the structured data provided. You do not speculate beyond what the
data supports. You state confidence honestly. You always flag risks that
would invalidate the thesis. Output must be valid JSON matching the provided
schema.
```

## Context payload

`ThesisContext` (see `trade_thesis.py`) serialises all of these fields
as JSON in the user message:

- **Spread state**: Brent, WTI, spread, 90d rolling mean/std, current
  Z-score, 5y percentile, days since the last |Z|>2 event.
- **Mean-reversion backtest**: hit rate, avg hold, avg PnL per bbl,
  max drawdown, Sharpe.
- **Inventory regime**: source tag (`EIA` / `FRED` / `unavailable`),
  current Mbbl, 4-week linear slope (bbls/day), 52-week slope,
  projected floor-breach date, days-of-supply.
- **Fleet composition**: total Mbbl on water, Jones Act / Shadow /
  Sanctioned breakdown, source tag, 30d delta if available.
- **Volatility regime**: 30-day realised vol of Brent / WTI / spread,
  plus the 1y percentile of spread vol.
- **Calendar & session**: next EIA release date (next Wednesday),
  NYMEX session open flag, weekend/holiday flag.
- **User threshold**: the sidebar Z-score alert level.

## Output schema (strict)

```json
{
  "stance": "long_spread" | "short_spread" | "flat",
  "conviction_0_to_10": 0,
  "time_horizon_days": 0,
  "entry": {
    "trigger_condition": "...",
    "suggested_z_level": 0.0,
    "suggested_spread_usd": 0.0
  },
  "exit": {
    "target_condition": "...",
    "target_z_level": 0.0,
    "stop_loss_condition": "...",
    "stop_z_level": 0.0
  },
  "position_sizing": {
    "method": "fixed_fractional" | "volatility_scaled" | "kelly",
    "suggested_pct_of_capital": 0.0,
    "rationale": "..."
  },
  "thesis_summary": "...",
  "key_drivers": ["...", "..."],
  "invalidation_risks": ["...", "..."],
  "catalyst_watchlist": [{"event": "...", "date": "YYYY-MM-DD", "expected_impact": "..."}],
  "data_caveats": ["...", "..."],
  "disclaimer_shown": true
}
```

`response_format={"type": "json_schema", "json_schema": {...}, "strict": true}`
is used — the model is physically prevented from returning anything that
doesn't match. If the JSON still fails to parse, we retry **once** with
a pointed "your previous output was not valid JSON" nudge. If that also
fails we fall through to the rule-based fallback.

## Guardrails (applied after model output, before render)

1. **Inventory missing → stance flat.** If `inventory_source` is
   `unavailable`, any non-flat stance is overwritten to `flat`,
   conviction capped at 3, and a caveat appended.
2. **Weak backtest → conviction cap.** If the model returns
   `conviction > 7` but the historical hit rate on |Z|>threshold
   entries is `< 55%`, conviction is downgraded to 5 and a
   calibration caveat is appended.
3. **Sizing cap.** Any `suggested_pct_of_capital > 20%` is clamped to
   20% with a caveat.
4. **Disclaimer always shown.** `disclaimer_shown` is forced to `true`.

## Fallback

If `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_KEY` are missing (local dev
without `.env`) or the API call raises, we emit a **rule-based thesis**
derived purely from the Z-score and backtest stats. The fallback is
clearly flagged in `data_caveats` and the UI mode badge flips to
"Rule-based fallback". The dashboard never blanks.

## Audit log

Every call — live or rule-based — appends one JSON line to
`data/trade_theses.jsonl` (gitignored). Schema:

```json
{"timestamp": "...", "source": "...", "model": "...",
 "context_fingerprint": "…16hex",
 "context": {...}, "thesis": {...},
 "guardrails": ["..."]}
```

Downstream we can grep these for a post-hoc hit-rate tracker.

## Caching

Tab 4 caches the thesis via `st.session_state` keyed on
`(context.fingerprint(), utc_hour, regenerate_button_tick)`.
Slider movement doesn't rebuild the thesis unless it changes a
fingerprinted field.

## Model

`gpt-4o-mini` (Azure OpenAI deployment `gpt-4o-mini`) — fast, cheap,
follows JSON schema reliably. To upgrade to `gpt-4o` or a reasoning
model, provision a new Azure OpenAI deployment and set
`AZURE_OPENAI_DEPLOYMENT` in App Settings.
