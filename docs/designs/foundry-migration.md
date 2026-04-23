# Foundry Agent Service migration — Design spec

> **Status:** PROPOSED (2026-04-23). Review target: 5 minutes.
> Skim the module surface + the env-var table + the FoundryThesisClient
> sketch + the feature-flag path, and you know how the 8-task plan
> hangs together.

## One-paragraph summary

We introduce a new module `foundry_agent.py` that wraps
`azure.ai.projects.AIProjectClient`. `trade_thesis.generate_thesis`
gains a `USE_FOUNDRY` feature-flag branch: when True, it delegates
to a `FoundryThesisClient` that reuses the existing
`THESIS_JSON_SCHEMA` verbatim as the agent's `response_format`; when
False, the existing AOAI path runs unchanged. Two persistent agents
are created at provision time — one on `gpt-5` (deep) and one on
`gpt-5-mini` (fast) — each registered with three function tools
(`run_cointegration`, `get_context_summary`, `run_backtest_on_window`)
and `code_interpreter` as an opt-in tool. Streaming flips from the
AOAI `stream=True` generator to Foundry's `create_stream` run, still
rendered by `st.write_stream` in `app.py`. The flag defaults False
until soak-verified on a canary thesis generation, then flips True
in App Settings. AOAI deployments stay live for a 7-day rollback
window; FT8 (separate later branch) deletes them.

## Module surface

Modified files:

```
trade_thesis.py        # add USE_FOUNDRY branch in generate_thesis;
                       #   keep the AOAI path byte-for-byte intact
requirements.txt       # + azure-ai-projects, + azure-identity
.env.example           # + new Foundry env vars, annotations
app.py                 # st.write_stream call site keeps working —
                       #   FoundryThesisClient.create_stream yields
                       #   compatible message deltas (single-line
                       #   change at the streaming call site)
```

New files:

```
foundry_agent.py       # FoundryThesisClient class — thin wrapper
                       #   around azure.ai.projects.AIProjectClient.
                       #   Agent resolve + thread + message + run +
                       #   tool dispatch + streaming helper.
infra/provision_foundry.sh
                       # Idempotent shell script — creates Hub +
                       #   Project + two model deployments (gpt-5
                       #   deep, gpt-5-mini fast), captures the
                       #   project connection string, writes it to
                       #   Key Vault, wires App Settings references.
                       #   Analogous to infra/provision_auth.sh.
tests/unit/test_foundry_agent.py
                       # Mocked-SDK unit tests (requests_mock /
                       #   transport=).
tests/integration/test_foundry_live.py
                       # @pytest.mark.live_foundry — runs only when
                       #   AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING
                       #   is present. CI-gated.
```

## New env vars

| Var | Purpose | Source |
| --- | --- | --- |
| `AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING` | Foundry project endpoint + auth handle | Key Vault reference, set by `provision_foundry.sh` |
| `AZURE_AI_FOUNDRY_AGENT_MODEL_FAST` | Fast-mode model deployment name | App Setting — default `gpt-5-mini` |
| `AZURE_AI_FOUNDRY_AGENT_MODEL_DEEP` | Deep-mode model deployment name | App Setting — default `gpt-5` |
| `USE_FOUNDRY` | Feature flag — `true` routes to Foundry, `false` (or unset) routes to AOAI | App Setting — default `false` |

All existing `AZURE_OPENAI_*` vars stay in place for the rollback
window.

## `FoundryThesisClient` — class sketch

```python
# foundry_agent.py
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

class FoundryThesisClient:
    """Thin wrapper around the Foundry AIProjectClient.

    Persistent agents (one per model) are created by provision_foundry.sh
    and their IDs are written to App Settings. This client looks them up
    by name at boot and caches the handle for the process lifetime.
    """

    def __init__(self, connection_string: str | None = None):
        self._client = AIProjectClient.from_connection_string(
            conn_str=connection_string or os.environ["AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING"],
            credential=DefaultAzureCredential(),
        )
        self._agent_cache: dict[str, str] = {}   # mode -> agent_id

    def _agent_id_for(self, mode: str) -> str:
        """Resolve (and cache) the agent_id for 'fast' or 'deep'."""

    def generate_thesis_json(
        self,
        mode: str,                    # "fast" | "deep"
        context_summary: dict,
        *,
        enable_code_interpreter: bool = False,
        thread_id: str | None = None,  # reuse thread for follow-ups
    ) -> tuple[dict, dict]:           # (parsed_json, meta)
        """Post a message, run, poll to completion, parse JSON per THESIS_JSON_SCHEMA."""

    def create_stream(
        self,
        mode: str,
        context_summary: dict,
        *,
        thread_id: str | None = None,
    ) -> Iterator[str]:
        """Yield text deltas compatible with st.write_stream."""
```

All tool-call handling is inside `generate_thesis_json` / `create_stream`
— the model asks, we dispatch to the registered Python callback,
post the tool result back to the run, re-poll.

## Agent creation

One persistent agent per mode, created by `provision_foundry.sh` (not
at runtime). Configuration:

```python
# pseudo-code — actual sits in provision_foundry.sh's python helper
project.agents.create_agent(
    name=f"macro-oil-thesis-{mode}",  # "macro-oil-thesis-fast" / "-deep"
    model=os.environ[f"AZURE_AI_FOUNDRY_AGENT_MODEL_{mode.upper()}"],
    instructions=SYSTEM_PROMPT,       # same SYSTEM_PROMPT from trade_thesis.py
    response_format={
        "type": "json_schema",
        "json_schema": THESIS_JSON_SCHEMA,   # VERBATIM the existing schema
    },
    tools=[
        {"type": "function", "function": RUN_COINTEGRATION_TOOL_DEF},
        {"type": "function", "function": GET_CONTEXT_SUMMARY_TOOL_DEF},
        {"type": "function", "function": RUN_BACKTEST_ON_WINDOW_TOOL_DEF},
        {"type": "code_interpreter"},   # enabled at agent level;
                                         # call-site gates whether it's
                                         # usable per-request via prompt
    ],
)
```

The `THESIS_JSON_SCHEMA` is imported from `trade_thesis.py` — not
re-specified. Single source of truth.

## Function tools — Python surface

```python
# foundry_agent.py

RUN_COINTEGRATION_TOOL_DEF = {
    "name": "run_cointegration",
    "description": "Engle-Granger cointegration test on two price series.",
    "parameters": {
        "type": "object",
        "properties": {
            "series1_json": {"type": "string", "description": "JSON-encoded list of Brent prices."},
            "series2_json": {"type": "string", "description": "JSON-encoded list of WTI prices."},
        },
        "required": ["series1_json", "series2_json"],
    },
}

def _tool_run_cointegration(series1_json: str, series2_json: str) -> dict:
    import json, pandas as pd
    from cointegration import engle_granger
    s1 = pd.Series(json.loads(series1_json))
    s2 = pd.Series(json.loads(series2_json))
    result = engle_granger(s1, s2)
    return {
        "p_value": result.p_value,
        "hedge_ratio": result.hedge_ratio,
        "half_life_days": result.half_life_days,
    }
```

Same pattern for `get_context_summary` (zero-arg, delegates to the
existing context-builder in `trade_thesis.py`) and
`run_backtest_on_window` (delegates to a small adapter over
`cointegration.backtest_zscore`). Each tool's output is strict JSON,
serialisable by the SDK's tool-response envelope.

The tool *definitions* are registered at agent-create time by
`provision_foundry.sh`; the tool *callbacks* are registered with the
Python SDK at `FoundryThesisClient.__init__` time.

## Streaming

Today, `app.py` renders a live thesis via `st.write_stream(
client.chat.completions.create(..., stream=True))`. Foundry's
equivalent is `project.agents.create_stream(thread_id, run_id,
assistant_id)` which yields event objects carrying
`MessageDelta.content[*].text.value`.

The `FoundryThesisClient.create_stream` helper adapts those events
into a plain string-delta iterator, which `st.write_stream` consumes
unchanged. One call-site in `app.py` swaps from the AOAI
stream-generator to `foundry_client.create_stream(...)` under the
`USE_FOUNDRY` flag.

## Feature flag — `USE_FOUNDRY`

```python
# trade_thesis.py (sketch — FT4 lands this)
def generate_thesis(context_summary: ContextSummary, mode: str = "fast") -> Thesis:
    if os.environ.get("USE_FOUNDRY", "").lower() in ("1", "true", "yes"):
        from foundry_agent import FoundryThesisClient
        client = FoundryThesisClient()
        parsed, meta = client.generate_thesis_json(mode, context_summary.to_dict())
        return _thesis_from_parsed(parsed, source=f"Foundry: {meta['model']}", meta=meta)
    # existing AOAI path — unchanged
    return _generate_thesis_aoai(context_summary, mode)
```

Default: `USE_FOUNDRY=false` (or unset).

Rollout:
- FT0–FT6 land with the flag False in all environments.
- FT7 finishing flow flips it True on one App Service instance
  (canary — the staging slot) for soak.
- After 24h of green canary, flip True on the prod slot.
- After 7 days of green prod, FT8 (separate branch) tears down the
  AOAI deployments.

Rollback: flip the App Setting to `false`, redeploy (CD picks it up
within 2 minutes). AOAI path is byte-for-byte intact during the
7-day window.

## Teardown plan

Gated behind FT8 (separate later branch):

1. After 7 days of `USE_FOUNDRY=true` in prod with no rollback,
   confirm no code path still imports or reads `AZURE_OPENAI_*` vars.
2. Delete the AOAI deployments (`gpt-4o-mini`, `gpt-4o`, `o4-mini`) via
   `az cognitiveservices account deployment delete`.
3. Rotate the AOAI API key in Key Vault to a dead value (belt + braces).
4. Remove the `_generate_thesis_aoai` function body, leave a stub
   that raises `RuntimeError("AOAI path removed — see FT8")`.
5. Remove `AZURE_OPENAI_*` from `.env.example` and from App Settings.
6. PROGRESS entry + SHA recorded in `docs/plans/foundry-migration.md`
   (this doc) under a "Teardown complete" appendix.

## Tests

**Mocked SDK unit tests** — `tests/unit/test_foundry_agent.py`.
Intercept the HTTP layer via `requests_mock` at the `azure-core`
transport boundary (the SDK accepts a `transport=` kwarg in its
pipeline config; we inject a fake transport in tests). The
alternative — `pytest-mock` patching `AIProjectClient.agents.*` —
is uglier and couples tests to SDK internals; prefer the transport
seam.

Tests we ship:

1. `test_foundry_client_init_reads_connection_string_from_env` —
   no env → `FoundryThesisClient()` raises a useful
   `FoundryConfigError`; with env → constructs OK.
2. `test_agent_id_for_fast_resolves_via_list_agents` — fake
   transport returns two agents; `_agent_id_for("fast")` returns
   the one whose name matches `macro-oil-thesis-fast`.
3. `test_generate_thesis_json_happy_path` — full run: post message,
   run steps through `queued → in_progress → completed`, returns a
   JSON-parsed thesis conforming to `THESIS_JSON_SCHEMA`.
4. `test_generate_thesis_json_dispatches_function_tool` — run
   transitions to `requires_action` with a `submit_tool_outputs`
   payload for `run_cointegration`; client dispatches to
   `_tool_run_cointegration`; submits result; run completes.
5. `test_tool_run_cointegration_parity_with_engle_granger` —
   build a synthetic Brent/WTI pair; call the tool wrapper and
   call `cointegration.engle_granger` directly; assert p_value,
   hedge_ratio, half_life_days match within 1e-6. (FT3's primary
   RED test.)
6. `test_generate_thesis_json_raises_on_run_failed` —
   fake transport returns `status="failed"`; client raises
   `FoundryRunError` with the run's last-error string.
7. `test_create_stream_yields_message_deltas` — fake transport
   yields three SSE events; client produces three string chunks.
8. `test_use_foundry_flag_routes_correctly` — in
   `tests/unit/test_trade_thesis.py`: patch `FoundryThesisClient` to
   return a canned thesis; set `USE_FOUNDRY=true`; call
   `generate_thesis`; assert the Foundry path was taken. Unset
   flag → assert AOAI path was taken.

**Dual-path schema test** — FT4's primary assertion: build a
deterministic ContextSummary; run both paths with mocked model
responses that echo the schema; assert both return a `Thesis` with
identical field presence (the dataclass shape matches).

**Live integration test** — `tests/integration/test_foundry_live.py`:

```python
import os, pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING"),
    reason="Foundry connection string not set",
)

@pytest.mark.live_foundry
def test_live_thesis_generation_fast_mode():
    from foundry_agent import FoundryThesisClient
    client = FoundryThesisClient()
    ctx = _build_minimal_context_for_test()
    parsed, meta = client.generate_thesis_json("fast", ctx)
    assert parsed["stance"] in ("long_spread", "short_spread", "flat")
    assert "thesis_summary" in parsed
    assert meta["model"].startswith("gpt-5")
```

CI never runs this by default (`@live_foundry` isn't collected).
`.github/workflows/live-foundry.yml` (a separate workflow, manual
dispatch only) runs it against the real project when we want to
verify post-deploy.

## Acceptance criteria

- All new unit tests pass in CI.
- `USE_FOUNDRY=true` locally + a populated connection string →
  `streamlit run app.py` renders a hero thesis whose
  `THESIS_SOURCE_META.source` prefix is `"Foundry:"` (not
  `"Azure OpenAI:"`).
- `USE_FOUNDRY=false` (unset) → existing AOAI behaviour byte-for-byte.
- `pytest -m live_foundry` against a real project returns a schema-
  valid thesis in both fast and deep modes.
- `provision_foundry.sh` is idempotent — second run no-ops cleanly.
- After 24h canary + 7d prod soak on `USE_FOUNDRY=true`, no AOAI
  API calls appear in App Insights for the `generate_thesis`
  code path.
- `THESIS_JSON_SCHEMA` is imported (not duplicated) in
  `foundry_agent.py` / `provision_foundry.sh`.

## Reversibility

- **Foundry regresses at runtime:** flip `USE_FOUNDRY` to `false` in
  App Settings. Next request hits AOAI. Zero code change.
- **gpt-5 is problematic:** change
  `AZURE_AI_FOUNDRY_AGENT_MODEL_DEEP` to `gpt-5-chat` or `gpt-4.1`
  in App Settings; agent automatically picks up the new model on
  next resolve (agents are looked up by name; model swap is an
  agent-update, handled by a re-run of `provision_foundry.sh`).
- **Tool dispatch misbehaves:** flip `USE_FOUNDRY=false`. The AOAI
  path doesn't use tools.
- **Full rollback to pre-Foundry:** revert the single merge commit
  of `feat/foundry-agent-migration`. `foundry_agent.py` and the
  provisioning script disappear; `trade_thesis.py` restores to the
  pre-flag shape; requirements drop the two new lines.

## Out of scope for this migration (explicit)

- **File-search-backed track record** — P2. The Foundry Agent
  Service supports `file_search` over a blob store, which would
  let the agent cite the live trade-record log when producing a
  thesis. Ship after Alpaca execute + track-record page land.
- **Chat-with-your-thesis (long-lived threads)** — P2. The
  infrastructure ships in this migration (every request creates a
  thread); the UI surface for "reply to this thesis" lands later.
- **Multi-tenant agent per user** — Phase 3. Today one pair of
  agents serves all users. When we have >1 user with
  per-user-customised instructions (prop desk vs retail), we'll
  split — but the single-agent model covers the current user base.
- **Scenario simulation UI** — P2. `code_interpreter` plumbing
  lands in FT6 but the user-facing "Run scenario" button is
  deferred.
- **AOAI teardown** — FT8 on a separate later branch after the
  7-day rollback window.
