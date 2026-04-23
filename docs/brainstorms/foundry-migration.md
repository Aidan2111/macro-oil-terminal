# Foundry Agent Service migration — Brainstorm

> **Status:** PROPOSED (2026-04-23). Brainstorm + design + plan land
> together on `main` as a single doc-only commit. No code, no Azure
> calls in this change. Implementation proceeds on
> `feat/foundry-agent-migration` once Aidan signs off on the five
> open questions at the bottom of this doc.

## The user problem, restated

Today `trade_thesis.py` constructs a single-shot chat-completion
against Azure OpenAI:

```python
from openai import AzureOpenAI
client = AzureOpenAI(endpoint=..., api_key=..., api_version=...)
client.chat.completions.create(
    model=deployment,
    response_format={"type": "json_schema", "json_schema": THESIS_JSON_SCHEMA},
    messages=[{"role": "system", ...}, {"role": "user", <context JSON blob>}],
)
```

That works — it's been shipping the hero thesis for months — but it
forces us into three shapes that increasingly don't fit:

1. **One-shot.** Every call is stateless. A user who reads a thesis
   and thinks "OK but what if oil draws 5mb next week?" has no
   runtime path to ask the model a follow-up. We'd have to rebuild
   the full context blob client-side and fire a second single-shot,
   with no memory of what the model already said. Threads-and-runs
   give us conversation continuity for free.
2. **We pre-package everything.** `generate_thesis` builds a large
   ContextSummary JSON before the call. If the model wants to know
   the half-life or a backtest on a particular z-window, we either
   pre-compute it (expensive when 95% of runs don't need it) or the
   model eyeballs it from the summary text (ungrounded). Function
   tools let the model *call* `run_cointegration`,
   `run_backtest_on_window`, and `get_context_summary` on demand, so
   we pay compute only for the slices a given run actually wants.
3. **No code execution.** The model can't run Python. If we want a
   scenario stress ("what does a $4 widening do to P&L over a
   10-day hold at z-entry 2?") the model approximates in prose. The
   `code_interpreter` tool — a managed sandboxed Python — lets the
   model compute the scenario, attach the result as a message part,
   and cite it in the thesis. Grounded scenario analysis instead of
   "the model's best guess".

Orthogonal to (1–3), **Aidan wants the GPT-5 upgrade**. GPT-5 (and
`gpt-5-mini` for the fast path) is live on Azure AI Foundry in the
regions we care about. The AOAI resource would also get us gpt-5,
but Foundry's agent runtime is the migration target we keep deferring
— and shipping gpt-5 is the forcing function to do it once rather
than twice.

## Why this matters now

- Hero thesis is stable. UI polish is in flight but doesn't touch
  the LLM surface. This is the calmest LLM-surface moment we'll get
  before Alpaca trade-execute lands and raises the blast radius of
  any LLM regression.
- GPT-5 is measurably better on structured-JSON tasks (Aidan's
  screenshot shows ~30% lower schema-violation rate on the AOAI
  eval harness). Wait-and-see costs us thesis quality today.
- The Foundry SDK (`azure.ai.projects.AIProjectClient`) stabilised
  in GA March 2026. Early-adopter risk is gone.

## Alternatives considered

### A. Keep AOAI, just upgrade the model to gpt-5

Change `AZURE_OPENAI_DEPLOYMENT_FAST=gpt-5-mini` and
`AZURE_OPENAI_DEPLOYMENT_DEEP=gpt-5` in App Settings. One-line
change. No SDK swap.

**Wins:** Smallest possible delta. Zero new infra. Zero new SDK.
Instant rollback (flip the two env vars back).

**Loses:** Doesn't solve problems (1), (2), or (3) above. We'd
still have a single-shot API with no threads, no function tools,
no code_interpreter. The gpt-5 upgrade is real, but we'd be
shipping it into the wrong runtime — and doing this now means
doing the Foundry migration *again* later against a moving
codebase.

### B. AOAI Assistants API (threads + tools on the same AOAI resource)

AOAI's Assistants preview exposes the same threads-and-runs +
function-tools surface as Foundry, but inside the existing
Azure-OpenAI resource. No new resource provider, no new
connection-string concept. Python surface is `openai.beta.assistants.*`
on the existing `AzureOpenAI` client.

**Wins:** No new resource. Small SDK delta (new `beta.*` namespace,
same client). Preserves the AOAI key-based auth we already have
working. Ships most of the Foundry *semantics* without the Foundry
org-chart.

**Loses:** AOAI Assistants is a preview surface that Microsoft has
signalled will converge *into* Foundry; the long-run investment is
the Foundry Agent Service. Picking AOAI Assistants means a second
migration in 6–12 months. Also: Foundry's `code_interpreter`
implementation is more mature (ships with pandas/numpy/statsmodels
preinstalled; AOAI Assistants `code_interpreter` has a narrower
stdlib image and is pricier per second). File-search is a P2 for
us but the Foundry version supports our existing blob-indexed
track-record store directly; AOAI Assistants wants a different
ingestion shape.

### C. Foundry Agent Service (full managed runtime)

Azure AI Foundry — Hub + Project, with an Agent created inside the
project. Agent gets one model deployment (gpt-5 for deep, gpt-5-mini
for fast), a set of function tools (our three Python functions),
`code_interpreter` enabled, and — eventually — `file_search` on the
track-record blob store. Each thesis request becomes a thread +
run; each follow-up is a new message on the same thread.

**Wins:** Solves (1), (2), (3) in one move. Where Microsoft's LLM
investment is heading — so the SDK and runtime only get more
capable, not less. `code_interpreter` comes with the scientific-
Python stack. Persistent threads unlock "chat with your oil
desk" (P2 UX). Function tools make cointegration etc. cheap
on-demand. Multi-tenant roadmap (one agent per user, Phase 3) is
a natural extension.

**Loses:** New resource-provider set (Hub + Project + connection
strings). New SDK (`azure-ai-projects` + `azure-identity`) — we
move from API-key auth to DefaultAzureCredential / managed
identity, which is strictly better for prod but new to wire up.
Per-call pricing has one more axis (tool-invocation seconds for
code_interpreter). Slightly higher cold-start latency on the
*first* call in a thread (~300ms for agent-resolve).

### D. Roll our own function-calling framework

Keep AOAI chat-completions, layer a tool-dispatch loop on top —
parse the `tool_calls` returned by the model, dispatch to our
Python functions, append the results as a `tool` message, call
again. The OpenAI cookbook has the reference pattern.

**Wins:** Zero new dependencies. Full control over the loop. No
new resource.

**Loses:** We end up re-implementing the primitive that the Agent
Service already wraps for us. No managed thread storage (we'd
persist threads in Table Storage ourselves). No `code_interpreter`
at all (we'd need a separate sandboxed-Python service — Modal,
Daytona, or a home-rolled Docker runner — and they each add
vendor risk + bill). Not reversible — if we later want to migrate
to Foundry, we throw all the loop code away anyway.

## Decision

**Alternative C — Foundry Agent Service**, with **Alternative B
(AOAI Assistants)** documented as the fallback we switch to only
if Foundry is unavailable in our region + GA window conflicts with
our ship date.

Rationale:

- *`code_interpreter` unblocks grounded scenario analysis.* The
  model can *actually compute* a stress P&L instead of eyeballing
  it from context. This is the single biggest thesis-quality
  unlock on the table.
- *Persistent threads unlock "chat with your oil desk".* P2 UX —
  "follow up on this thesis" becomes a natural extension, not a
  second migration.
- *Function tools decouple context packaging from prompt
  engineering.* Today we spend prompt tokens on a big
  ContextSummary JSON that the model may or may not use. Tools
  invert the flow: the model asks for what it needs. Cheaper tokens,
  better grounding.
- *gpt-5 comes along for the ride.* The model upgrade ships as
  part of the agent-create config, not as a separate env-var
  swap.
- *Reversibility.* `USE_FOUNDRY` feature flag. Default False until
  soak-verified. Flip to True in App Settings. Flip back in one
  env-var edit if anything regresses. AOAI deployments stay live
  for a 7-day rollback window after default-on.
- *Skills-match.* We already speak `azure-identity` (Key Vault,
  Table Storage managed-identity). Foundry's auth story is a
  drop-in extension.

AOAI Assistants is the documented fallback — if gpt-5 on Foundry
slips in our region, we fall back to AOAI Assistants + gpt-5 on
the existing AOAI resource with the same threads-and-runs shape;
the client wrapper's surface is similar enough that the swap is
local to `foundry_agent.py`.

## Model-deployment shape

- **Deep mode** (reasoning / "Deep analysis" toggle): `gpt-5`.
- **Fast mode** (default / "Quick read"): `gpt-5-mini`.
- **Fallback if gpt-5 not yet deployable in eastus**: `gpt-5-chat`,
  then `gpt-4.1`, then highest available in the region. Recorded
  in `THESIS_SOURCE_META` so we can see in the UI which model
  produced any given thesis.

Reasoning: gpt-5-mini is measurably cheaper and faster for the
structured-JSON path; gpt-5 is worth the cost when the user
explicitly asks for the reasoning trace. Same fast/deep split we
already have — we're just swapping the models underneath.

## Cost envelope

Rough back-of-envelope, per thesis call, using Foundry public
pricing at 2026-04-23:

| Path | Input | Output | Code-interp | Est. $/call |
| --- | --- | --- | --- | --- |
| Fast (gpt-5-mini, no code-interp) | ~4k tok | ~1.5k tok | — | $0.008 |
| Deep (gpt-5, no code-interp) | ~6k tok | ~3k tok | — | $0.060 |
| Deep + scenario (gpt-5 + code-interp ~8s) | ~6k tok | ~3k tok | 8 tool-seconds | $0.090 |

At hero-thesis cadence (one generation per page load, cached 5
min via the existing liveness layer, say 100 gens/day at steady
state) that's ~$1-$9/day depending on deep/fast mix. Well inside
the informal ceiling.

## Function tools we expose at agent-create time

Three tools, all thin wrappers around existing Python functions.
No new math.

1. **`run_cointegration(series1_json, series2_json) -> {p_value, hedge_ratio, half_life_days}`**
   — wraps `cointegration.engle_granger`. JSON-serialisable input
   so the model can send it, JSON-serialisable output so the
   model can read it. Tests: parity vs direct Python call must
   match within 1e-6 on the same input.

2. **`get_context_summary() -> ContextSummary`** — wraps the
   existing context-builder. Zero-argument, returns the same
   JSON blob `generate_thesis` currently passes up-front. Lets
   us stop pushing the whole context into the prompt by default;
   the model can ask for it only when it needs it.

3. **`run_backtest_on_window(start, end, entry_z, exit_z) -> backtest_stats`**
   — wraps a small wrapper around `cointegration.backtest_zscore`
   (or equivalent — finalise in design). Returns `{n_trades,
   win_rate, avg_pnl_pct, max_dd_pct, sharpe}`. This is the tool
   that makes "what if we'd run this at z=1.8 last month?" a
   one-line question for the model.

A fourth tool — `scenario_simulate(…)` via `code_interpreter` — is
plumbing only in P1.M1; actual UI surfacing is P2.

## Unknowns / open questions for Aidan

Apply the "most-conservative, minimal, reversible" default on
anything Aidan doesn't explicitly overrule.

1. **gpt-5 vs gpt-5-mini deployment mix.** **Proposed default:
   `gpt-5` for deep, `gpt-5-mini` for fast.** If gpt-5 isn't
   deployable in eastus, fall back to `gpt-5-chat`, then
   `gpt-4.1`, then the highest available. Record the chosen
   model in `THESIS_SOURCE_META` so the UI surfaces it.

2. **`code_interpreter` cost budget.** Every-run-enabled vs
   per-request flag? **Proposed default: per-request opt-in flag
   on the thesis generation call** (`enable_code_interpreter:
   bool = False`). Deep mode in the UI sets it True; fast mode
   leaves it False. Keeps the fast-path free of tool-second
   billing. When we surface "Run scenario" as a UI button in P2,
   the button flips the flag for that specific call.

3. **Chat-with-thread UX — P2 or P3?** Persistent threads give us
   the capability today. The product question is when to surface
   it. **Proposed default: P2 (i.e. next phase after this
   migration plus the Alpaca execute work).** Ship the
   infrastructure in P1.M (this branch) so threads are already
   persisted; wire the UI in P2.

4. **AOAI fallback lifespan.** Once `USE_FOUNDRY=True` by default
   in prod, how long do we keep AOAI deployments alive for
   rollback? **Proposed default: 7 days of soak after
   default-on, then teardown** (FT8, separate later branch). 7
   days covers two weekday cycles + one weekend — enough to
   catch any cadence-dependent regression.

5. **Credential strategy — managed identity or API key?**
   Foundry supports both. Managed identity is the prod-grade
   path (no secrets in Key Vault for the connection string
   itself). **Proposed default: managed identity for the App
   Service, API key in `.env` for local dev**. Mirrors the
   pattern we already use for Table Storage and Key Vault.

## Residual default

Anything else that surfaces and isn't covered here: apply the
"most-conservative, minimal, reversible" rule. Behind
`USE_FOUNDRY=False` by default. AOAI path stays intact until the
7-day rollback window closes after default-on. Record the
decision + reasoning in PROGRESS.md and move on.
