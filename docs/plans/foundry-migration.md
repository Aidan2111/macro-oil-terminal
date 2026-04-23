# Foundry Agent Service migration — Plan

> **Status:** PROPOSED (2026-04-23). Brainstorm + design + plan land
> together on `main` as one doc-only commit. Implementation branch
> `feat/foundry-agent-migration` off `main` (HEAD `e8fb214` or
> newer) cuts after Aidan greenlights the five open questions in
> the brainstorm.
> **Rhythm:** one fresh subagent per task, RED → GREEN → REFACTOR →
> commit. Two-stage review (spec-compliance + code-quality) between
> tasks. Same loop as P1.1 / hero-thesis / UI-polish.
> **Target:** 6–8 commits on the branch before merge (FT1..FT7).
> FT8 teardown is a separate later branch after the 7-day rollback
> window.

## Definition of done

- All new unit tests (8 in the design spec) + the dual-path schema
  test in `test_trade_thesis.py` pass locally and in CI.
- `USE_FOUNDRY=true` + live connection string → hero thesis
  renders with source prefix `"Foundry:"`.
- `USE_FOUNDRY=false` → AOAI path byte-for-byte unchanged, all
  existing tests still green.
- `provision_foundry.sh` idempotent; re-runnable without
  error.
- Three function tools (`run_cointegration`,
  `get_context_summary`, `run_backtest_on_window`) registered at
  agent-create time; cointegration parity test passes within 1e-6
  of direct Python call.
- `code_interpreter` plumbing present; per-request opt-in flag on
  `generate_thesis_json` defaults False.
- Canary soak on staging (24h) + prod soak (7d) both green before
  FT8 teardown even considered.
- PROGRESS.md entry with merge SHA.

---

## FT0 — Provision Hub + Project + model deployments

**Not a RED/GREEN task** — Aidan runs this on the host once the
plan is approved. Doc-only deliverable in this branch; the actual
`az` calls happen as a signup step.

**Steps:**

1. Aidan runs `infra/provision_foundry.sh` on the host (the
   script itself is delivered by FT2).
2. Script creates:
   - Azure AI Foundry Hub in resource group `oil-price-tracker`,
     region `eastus` (or closest if gpt-5 not yet deployable).
   - Foundry Project named `macro-oil-terminal` inside the Hub.
   - Two model deployments inside the project:
     - `gpt-5` (deep mode)
     - `gpt-5-mini` (fast mode)
   - Fallback chain if gpt-5 unavailable: `gpt-5-chat` → `gpt-4.1`.
3. Capture the project connection string and write it to Key
   Vault as secret `ai-foundry-project-connection-string`.
4. Set four App Settings (Key Vault references where appropriate)
   on both `oil-tracker-app-canadaeast-4474` *and* any staging
   slot:
   - `AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING` (Key Vault ref)
   - `AZURE_AI_FOUNDRY_AGENT_MODEL_FAST=gpt-5-mini`
   - `AZURE_AI_FOUNDRY_AGENT_MODEL_DEEP=gpt-5`
   - `USE_FOUNDRY=false`
5. The agent-create step (two persistent agents) happens inside
   the script too, using the same THESIS_JSON_SCHEMA sourced via
   `python -c "from trade_thesis import THESIS_JSON_SCHEMA; print(json.dumps(...))"`
   so the schema can't drift between AOAI and Foundry paths.

**Waiting on Aidan:** this is the only "Aidan runs a CLI" step.
Everything else is code.

---

## FT1 — Dependencies land

**Red:** `tests/unit/test_foundry_deps_import.py`:

1. `test_azure_ai_projects_importable` — `import azure.ai.projects`
   succeeds; `azure.ai.projects.__version__` is present.
2. `test_azure_identity_default_credential_constructible` —
   `from azure.identity import DefaultAzureCredential;
   DefaultAzureCredential()` doesn't raise.

**Green:** add to `requirements.txt`:

```
azure-ai-projects>=1.0.0
azure-identity>=1.15.0
```

**Refactor:** none — one-line additions.

**Commit:** `feat(foundry): add azure-ai-projects + azure-identity deps (FT1)`.

---

## FT2 — `FoundryThesisClient` scaffolding

**Red:** `tests/unit/test_foundry_agent.py` — tests 1, 2, 3, 6 from
the design spec's test list:

1. `test_foundry_client_init_reads_connection_string_from_env` —
   empty env → `FoundryConfigError`; set env → constructs OK.
2. `test_agent_id_for_fast_resolves_via_list_agents` — fake
   transport returns two agents; resolver picks the fast one by
   name.
3. `test_generate_thesis_json_happy_path` — full run, no tools,
   returns JSON-parsed thesis matching `THESIS_JSON_SCHEMA`
   required fields.
6. `test_generate_thesis_json_raises_on_run_failed` — run status
   `failed` → `FoundryRunError`.

**Green:** create `foundry_agent.py`:

- `FoundryThesisClient.__init__` (env read + `AIProjectClient`
  construct).
- `_agent_id_for(mode)` with in-memory cache.
- `generate_thesis_json(mode, context_summary, *, enable_code_interpreter=False, thread_id=None)`
  — post thread, post message, start run, poll to completion,
  parse message as JSON.
- `FoundryConfigError`, `FoundryRunError` exception classes.
- No tool-dispatch yet — that lands in FT3.

**Refactor:** extract a small `_poll_run_to_terminal(run_id)` helper
so later tasks (tool dispatch, streaming) can reuse it.

**Commit:** `feat(foundry): FoundryThesisClient scaffolding — agents, threads, runs (FT2)`.

---

## FT3 — Function tools + tool-dispatch loop

**Red (primary — parity test):** extend
`tests/unit/test_foundry_agent.py` with tests 4 and 5 from the
design spec:

4. `test_generate_thesis_json_dispatches_function_tool` — run
   transitions to `requires_action` with a
   `submit_tool_outputs` payload for `run_cointegration`; client
   dispatches to the Python callback; submits result; run
   completes.
5. **`test_tool_run_cointegration_parity_with_engle_granger`** —
   build a synthetic Brent/WTI pair (fixed seed). Call
   `_tool_run_cointegration(series1_json, series2_json)` and
   directly call `cointegration.engle_granger(s1, s2)`. Assert
   `p_value`, `hedge_ratio`, `half_life_days` match within 1e-6.
   This is the test that must never flake — it's the contract
   between model-facing tools and the underlying math.

Plus:

- `test_tool_get_context_summary_returns_expected_shape` — mock
  the context-builder; assert the tool wrapper's return dict has
  the same keys as the direct call.
- `test_tool_run_backtest_on_window_returns_stats_schema` —
  assert `{n_trades, win_rate, avg_pnl_pct, max_dd_pct, sharpe}`
  keys all present.

**Green:** in `foundry_agent.py`:

- Tool definitions: `RUN_COINTEGRATION_TOOL_DEF`,
  `GET_CONTEXT_SUMMARY_TOOL_DEF`,
  `RUN_BACKTEST_ON_WINDOW_TOOL_DEF` (OpenAI-function-style JSON
  schemas).
- Python callbacks: `_tool_run_cointegration`,
  `_tool_get_context_summary`, `_tool_run_backtest_on_window`.
- `_dispatch_tool_calls(run)` — iterates over `run.required_action.
  submit_tool_outputs.tool_calls`, dispatches by `function.name`,
  collects outputs, submits via `project.agents.submit_tool_outputs(...)`.
- Extend the polling loop in `generate_thesis_json` to handle
  `requires_action` by calling `_dispatch_tool_calls` and
  re-polling.

**Refactor:** pull the tool registry (`{name: callback}`) into a
module-level dict so FT6's code_interpreter wiring drops in next
to it.

**Commit:** `feat(foundry): register + dispatch 3 function tools; cointegration parity test (FT3)`.

---

## FT4 — `USE_FOUNDRY` feature flag + dual-path assertion

**Red:** extend `tests/unit/test_trade_thesis.py`:

1. `test_use_foundry_true_routes_to_foundry_client` — set
   `USE_FOUNDRY=true`; patch `FoundryThesisClient.generate_thesis_json`
   to return a canned `(parsed, meta)`; call `generate_thesis(ctx)`;
   assert the Foundry path ran and the returned `Thesis.source`
   starts with `"Foundry:"`.
2. `test_use_foundry_false_routes_to_aoai` — unset / "false";
   patch the AOAI code path; assert AOAI ran, Foundry did not.
3. `test_use_foundry_unset_defaults_to_aoai` — no env var at all
   → AOAI path runs.
4. **Dual-path schema parity:** `test_both_paths_return_same_thesis_shape`
   — build a deterministic `ContextSummary`. Run both paths with
   mocked model responses that echo a canonical JSON conforming
   to `THESIS_JSON_SCHEMA`. Assert `dataclasses.fields(thesis_a)`
   ==  `dataclasses.fields(thesis_b)` and that no required field
   is None in either.

**Green:** in `trade_thesis.generate_thesis`, add the branch:

```python
if os.environ.get("USE_FOUNDRY", "").lower() in ("1", "true", "yes"):
    from foundry_agent import FoundryThesisClient
    client = FoundryThesisClient()
    parsed, meta = client.generate_thesis_json(
        mode, context_summary.to_dict(),
        enable_code_interpreter=(mode == "deep"),
    )
    return _thesis_from_parsed(parsed, source=f"Foundry: {meta['model']}", meta=meta)
# existing AOAI path — unchanged
```

Extract the existing AOAI path into a private `_generate_thesis_aoai`
so the branch is readable and FT8's teardown has a single target
function.

**Refactor:** module-level `_should_use_foundry()` helper so the
string-matching semantics (1/true/yes/on, case-insensitive) are
defined once.

**Commit:** `feat(foundry): USE_FOUNDRY flag + dual-path schema parity test (FT4)`.

---

## FT5 — Streaming via `create_stream`

**Red:** extend `tests/unit/test_foundry_agent.py`:

7. `test_create_stream_yields_message_deltas` — fake SSE transport
   yields three `MessageDelta` events with text payloads "Spread ",
   "dislocated ", "2.8σ"; `FoundryThesisClient.create_stream(...)`
   yields three string chunks in order.

Plus a small e2e-style assertion:

- `test_app_py_write_stream_integration` (unit-level, patched
  Streamlit): with `USE_FOUNDRY=true`, the code path in `app.py`
  that streams the thesis calls
  `foundry_client.create_stream(...)` (not the AOAI generator).

**Green:**

- Implement `FoundryThesisClient.create_stream(mode, context_summary,
  *, thread_id=None) -> Iterator[str]` — wraps
  `project.agents.create_stream(...)`, extracts
  `event.data.delta.content[0].text.value` per event, yields
  the string.
- One edit in `app.py` at the streaming call-site: branch on
  `USE_FOUNDRY`, call the new helper when True.

**Refactor:** keep the AOAI stream generator as-is — don't fold it
into `create_stream`. Two stream paths, one flag.

**Commit:** `feat(foundry): create_stream path + app.py write_stream call-site (FT5)`.

---

## FT6 — `code_interpreter` tool (plumbing only)

**Red:** `tests/unit/test_foundry_agent.py`:

- `test_code_interpreter_tool_registered_at_agent_create` — mock
  the agent-create transport; assert the `tools` payload includes
  `{"type": "code_interpreter"}`. (This test asserts the
  `provision_foundry.sh`-driven config via an intermediate helper
  function `_agent_tools_spec(enable_code_interpreter=True)` that
  both the script and the test import.)
- `test_generate_thesis_json_passes_code_interpreter_hint` — when
  `enable_code_interpreter=True`, the system/user message includes
  a one-line hint that the code_interpreter tool is available
  (otherwise the model ignores tools it's registered with by
  default — Foundry convention).
- `test_generate_thesis_json_respects_default_false` — default
  call does not include the hint.

**Green:**

- Add `_agent_tools_spec(enable_code_interpreter: bool)` returning
  the tool list shape used at agent-create time.
- In `generate_thesis_json`, conditionally append a short
  "You have a Python code-interpreter available for scenario
  analysis; use it only if asked." line to the user message when
  the flag is True.
- Update `provision_foundry.sh` (FT2's deliverable) to include the
  code_interpreter tool in the agents' tool list.

**Refactor:** none.

**Commit:** `feat(foundry): code_interpreter plumbing + per-request opt-in flag (FT6)`.

---

## FT7 — Finishing flow (not RED/GREEN — `finishing-a-development-branch` skill)

1. Merge `main` into `feat/foundry-agent-migration`; resolve
   conflicts.
2. Run full pytest locally — all new tests + the existing 200+
   tests must pass. AOAI path (flag False) must still produce a
   schema-valid thesis against the live AOAI resource.
3. Run one live `pytest -m live_foundry` against the real project
   — both fast and deep modes.
4. Screenshot the hero thesis with `THESIS_SOURCE_META.source`
   reading `"Foundry: gpt-5-mini"` (fast) / `"Foundry: gpt-5"`
   (deep). Attach to PR.
5. Push branch, open PR, CI runs.
6. Merge to `main` via `--no-ff`. CD deploys with
   `USE_FOUNDRY=false` still — nothing changes for users yet.
7. **Canary flip:** set `USE_FOUNDRY=true` on the staging slot
   only. Run `./agent-scripts/verify_hero_live.py` against
   staging; manual smoke test. Hold 24h.
8. **Prod flip:** set `USE_FOUNDRY=true` on prod App Service.
   Run live-verify against prod. Hold 7d. Monitor App Insights
   for error spikes on `generate_thesis`.
9. PROGRESS.md entry, merge SHA + canary + prod-flip timestamps.
10. **Then and only then**, cut the FT8 teardown branch.

**Commit (merge):** `Merge feat/foundry-agent-migration: AOAI → Foundry Agent Service + gpt-5 (P1.M)`.

---

## FT8 — AOAI teardown (separate later branch)

**Branch:** `feat/foundry-aoai-teardown` off `main`, after 7d prod
soak green. Not part of the 6–8-commit target for
`feat/foundry-agent-migration`.

1. Confirm via App Insights that zero `generate_thesis` calls have
   hit AOAI in the prior 7 days.
2. Delete AOAI deployments:
   - `az cognitiveservices account deployment delete ... gpt-4o-mini`
   - `az cognitiveservices account deployment delete ... gpt-4o`
   - `az cognitiveservices account deployment delete ... o4-mini`
3. Rotate `AZURE_OPENAI_KEY` in Key Vault to a dead sentinel.
4. In `trade_thesis.py`: replace `_generate_thesis_aoai` body
   with `raise RuntimeError("AOAI path removed in FT8; see
   docs/plans/foundry-migration.md")`.
5. Remove `AZURE_OPENAI_*` from `.env.example` and `_deployment_for`,
   and from App Settings on all slots.
6. Remove the `USE_FOUNDRY` branch from `generate_thesis` (flag is
   now permanently effective).
7. Update `docs/plans/foundry-migration.md` (this file) with a
   "Teardown complete" appendix + SHAs.

**Commit:** `chore(foundry): tear down AOAI — Foundry is the only path (FT8)`.

---

## Open risks / known unknowns

- **gpt-5 region availability.** If gpt-5 isn't deployable in
  `eastus` at FT0 time, `provision_foundry.sh` has a documented
  fallback: `gpt-5-chat` → `gpt-4.1` → highest available. Record
  the chosen model in PROGRESS.
- **Tool dispatch latency.** Each tool call adds ~300–800ms
  round-trip (model pause → tool dispatch → result submit → model
  resume). If the deep-mode thesis regularly invokes 3 tools, we
  add ~1.5–2.5s to TTFT. Mitigation: measure in the canary window;
  if user-visible, pre-cache the `get_context_summary` result at
  the app layer so the tool call returns instantly on the hot path.
- **Managed-identity role assignment.** The App Service's managed
  identity needs `Azure AI Developer` role on the Foundry project.
  If this isn't in place when `USE_FOUNDRY=true` flips, every call
  401s. Mitigation: `provision_foundry.sh` grants the role
  explicitly; live-verify step in FT7 checks the first call
  returns 200 before we move to prod.
- **Connection-string rotation.** Foundry project connection
  strings include a resource-scoped key. If the key rotates, the
  Key Vault reference needs to be updated. Mitigation: document
  the rotation procedure in `DEPLOY.md` as part of FT2.
- **Schema drift between AOAI and Foundry paths during the
  rollback window.** If we edit `THESIS_JSON_SCHEMA` during the
  7-day window, both paths must re-parse consistently. Mitigation:
  the schema is *imported* by both paths; dual-path schema test
  in FT4 catches any drift at CI time.

## Checklist to greenlight the plan

- [ ] Aidan has greenlit the five open questions in the brainstorm.
- [ ] gpt-5 + gpt-5-mini availability confirmed in the target
      region.
- [ ] App Service managed identity role-assignment path decided
      (managed-identity vs API-key; default managed-identity).
- [ ] AOAI fallback window confirmed at 7 days.
- [ ] `code_interpreter` cost budget confirmed (per-request
      opt-in, deep mode only by default).
