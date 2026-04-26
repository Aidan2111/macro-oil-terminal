"""Unit tests for the Foundry-backed thesis generator.

Strategy
--------
The Foundry SDK pipeline is mocked at the seam where
``backend.services.trade_thesis_foundry._make_openai_client`` is invoked —
we substitute a fake OpenAI client that exposes the
``client.beta.assistants.*`` and ``client.beta.threads.*`` surface used
by ``_run_agent``. This keeps tests aligned with the public SDK shape
without coupling to ``azure-core`` transport internals.

Coverage
--------
1.  Module imports cleanly (azure-ai-projects + azure-identity available).
2.  Tool dispatch table contains the six required tools + code interpreter.
3.  Tool spec (registered with the assistant) has function tools and a
    code_interpreter entry, matching the design spec.
4.  ``_make_openai_client`` raises ``FoundryConfigError`` when no endpoint
    env var is set.
5.  ``_resolve_assistant`` reuses an existing assistant by name.
6.  ``_resolve_assistant`` creates one when none matches.
7.  ``generate_thesis_foundry`` happy path — thread/message/run flow,
    JSON parsing, ``Thesis`` shape parity with the AOAI path.
8.  ``generate_thesis_foundry`` dispatches a ``requires_action``
    function-tool call back into the Python tool layer.
9.  ``generate_thesis_foundry`` raises ``FoundryRunError`` on
    ``status=failed``.
10. ``trade_thesis.generate_thesis`` routes to the Foundry path when
    ``USE_FOUNDRY=true`` and to the AOAI path otherwise.
11. Integration smoke: skipped unless ``RUN_FOUNDRY_SMOKE=1``.
"""

from __future__ import annotations

import json
import os
import types
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Fake OpenAI client — minimal surface mirroring openai.OpenAI.beta.*
# ---------------------------------------------------------------------------
class _FakeAttr:
    """Tiny attribute bag — same as types.SimpleNamespace but readable."""

    def __init__(self, **kw: Any) -> None:
        for k, v in kw.items():
            setattr(self, k, v)


def _make_canonical_thesis_payload() -> dict:
    """Return a JSON payload that satisfies THESIS_JSON_SCHEMA."""
    return {
        "stance": "long_spread",
        "conviction_0_to_10": 6.5,
        "time_horizon_days": 21,
        "entry": {
            "trigger_condition": "Spread Z holds above +2σ at NY open",
            "suggested_z_level": 2.3,
            "suggested_spread_usd": 4.10,
        },
        "exit": {
            "target_condition": "Z reverts through 0.5σ",
            "target_z_level": 0.5,
            "stop_loss_condition": "Z extends past +3σ",
            "stop_z_level": 3.0,
        },
        "position_sizing": {
            "method": "fixed_fractional",
            "suggested_pct_of_capital": 4.0,
            "rationale": "Sized below the 20% policy cap; vol regime mid.",
        },
        "thesis_summary": (
            "Brent-WTI spread at +2.3σ stretch with declining inventory "
            "supports a mean-reversion long_spread."
        ),
        "key_drivers": [
            "Spread Z +2.3σ vs 90-day mean",
            "Cushing inventory falling 4w slope",
            "MM net positioning at 75th percentile",
        ],
        "invalidation_risks": [
            "Structural break in Brent-WTI arb",
            "Sustained low liquidity at entry",
        ],
        "catalyst_watchlist": [
            {
                "event": "EIA weekly release",
                "date": "2026-04-30",
                "expected_impact": "Could compress spread 0.5σ on draw.",
            }
        ],
        "data_caveats": [],
        "disclaimer_shown": True,
        "reasoning_summary": "Stretch + inventory tailwind → long_spread.",
        "plain_english_headline": (
            "Brent is unusually expensive vs WTI right now, and inventories "
            "are falling — the model suggests betting the gap closes."
        ),
    }


class _FakeAssistantsAPI:
    def __init__(self, fake_client: "_FakeOpenAIClient") -> None:
        self._client = fake_client

    def list(self, *, limit: int = 100) -> Any:
        return _FakeAttr(data=list(self._client.assistants))

    def create(self, *, model: str, name: str, instructions: str, tools: list, response_format: dict) -> Any:
        a = _FakeAttr(id=f"asst_{name}", name=name, model=model, tools=tools)
        self._client.assistants.append(a)
        self._client.create_calls.append(
            {"model": model, "name": name, "tools": tools, "response_format": response_format}
        )
        return a


class _FakeThreadMessagesAPI:
    def __init__(self, client: "_FakeOpenAIClient") -> None:
        self._client = client

    def create(self, *, thread_id: str, role: str, content: str) -> Any:
        msg = _FakeAttr(id=f"msg_user_{len(self._client.user_messages)}", role=role)
        self._client.user_messages.append(content)
        return msg

    def list(self, *, thread_id: str, order: str = "desc", limit: int = 10) -> Any:
        # Newest first — assistant_text is the assistant's last message.
        text_part = _FakeAttr(value=self._client.assistant_text or "{}")
        msg = _FakeAttr(role="assistant", content=[_FakeAttr(text=text_part)])
        return _FakeAttr(data=[msg])


class _FakeThreadRunsAPI:
    def __init__(self, client: "_FakeOpenAIClient") -> None:
        self._client = client

    def create(self, *, thread_id: str, assistant_id: str) -> Any:
        # First state pulled from the script.
        return self._client._next_run_state()

    def retrieve(self, *, thread_id: str, run_id: str) -> Any:
        return self._client._next_run_state()

    def submit_tool_outputs(self, *, thread_id: str, run_id: str, tool_outputs: list) -> Any:
        self._client.tool_outputs_submitted.extend(tool_outputs)
        return self._client._next_run_state()


class _FakeThreadsAPI:
    def __init__(self, client: "_FakeOpenAIClient") -> None:
        self._client = client
        self.messages = _FakeThreadMessagesAPI(client)
        self.runs = _FakeThreadRunsAPI(client)

    def create(self) -> Any:
        return _FakeAttr(id="thread_test_001")


class _FakeBeta:
    def __init__(self, client: "_FakeOpenAIClient") -> None:
        self.assistants = _FakeAssistantsAPI(client)
        self.threads = _FakeThreadsAPI(client)


class _FakeOpenAIClient:
    """Drop-in replacement for the openai.OpenAI client surface we use.

    The ``run_states`` queue is the script the test wants to walk —
    each retrieve / create / submit_tool_outputs pops from the front.
    """

    def __init__(
        self,
        *,
        run_states: list,
        assistant_text: str | None = None,
        existing_assistants: list | None = None,
    ) -> None:
        self.run_states = list(run_states)
        self.assistant_text = assistant_text
        self.assistants = list(existing_assistants or [])
        self.create_calls: list[dict] = []
        self.user_messages: list[str] = []
        self.tool_outputs_submitted: list = []
        self.beta = _FakeBeta(self)

    def _next_run_state(self) -> Any:
        if not self.run_states:
            return _FakeAttr(id="run_test_001", status="completed", required_action=None, last_error=None)
        s = self.run_states.pop(0)
        return s


def _run_state(status: str, *, required_action: Any = None, last_error: Any = None, run_id: str = "run_test_001") -> Any:
    return _FakeAttr(id=run_id, status=status, required_action=required_action, last_error=last_error)


def _required_action(tool_name: str, args: dict, *, call_id: str = "call_001") -> Any:
    return _FakeAttr(
        type="submit_tool_outputs",
        submit_tool_outputs=_FakeAttr(
            tool_calls=[
                _FakeAttr(
                    id=call_id,
                    type="function",
                    function=_FakeAttr(name=tool_name, arguments=json.dumps(args)),
                )
            ]
        ),
    )


# ---------------------------------------------------------------------------
# 1) Module imports cleanly
# ---------------------------------------------------------------------------
def test_module_imports():
    """The Foundry module must import without azure-ai-projects errors."""
    from backend.services import trade_thesis_foundry as ftt

    assert hasattr(ftt, "generate_thesis_foundry")
    assert hasattr(ftt, "FoundryConfigError")
    assert hasattr(ftt, "FoundryRunError")


# ---------------------------------------------------------------------------
# 2) Tool dispatch table contains the six required tools
# ---------------------------------------------------------------------------
def test_tool_dispatch_has_required_six_tools():
    from backend.services.trade_thesis_foundry import _TOOL_DISPATCH

    expected = {
        "get_current_spread",
        "get_inventory_state",
        "get_cftc_positioning",
        "get_fleet_summary",
        "run_cointegration",
        "run_backtest_window",
    }
    assert expected.issubset(set(_TOOL_DISPATCH.keys())), (
        f"missing tools: {expected - set(_TOOL_DISPATCH.keys())}"
    )


# ---------------------------------------------------------------------------
# 3) Tool spec contains all six function tools + code_interpreter
# ---------------------------------------------------------------------------
def test_tool_specs_register_function_tools_and_code_interpreter():
    from backend.services.trade_thesis_foundry import _build_tool_specs

    specs = _build_tool_specs()
    fn_names = {
        s["function"]["name"]
        for s in specs
        if s.get("type") == "function" and "function" in s
    }
    assert fn_names == {
        "get_current_spread",
        "get_inventory_state",
        "get_cftc_positioning",
        "get_fleet_summary",
        "run_cointegration",
        "run_backtest_window",
    }
    types_present = {s.get("type") for s in specs}
    assert "code_interpreter" in types_present, (
        f"code_interpreter not registered; got types {types_present}"
    )


# ---------------------------------------------------------------------------
# 4) Missing endpoint raises FoundryConfigError
# ---------------------------------------------------------------------------
def test_make_openai_client_raises_without_endpoint(monkeypatch):
    from backend.services.trade_thesis_foundry import (
        FoundryConfigError,
        _project_endpoint,
    )

    monkeypatch.delenv("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING", raising=False)
    with pytest.raises(FoundryConfigError):
        _project_endpoint()


def test_make_openai_client_accepts_legacy_connection_string_var(monkeypatch):
    from backend.services.trade_thesis_foundry import _project_endpoint

    monkeypatch.delenv("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv(
        "AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING",
        "https://example.services.ai.azure.com/api/projects/_project",
    )
    assert _project_endpoint().endswith("_project")


# ---------------------------------------------------------------------------
# 5/6) Assistant resolution
# ---------------------------------------------------------------------------
def test_resolve_assistant_reuses_existing_by_name():
    from backend.services.trade_thesis_foundry import _resolve_assistant

    existing = [_FakeAttr(id="asst_existing_fast", name="macro-oil-thesis-fast")]
    fake = _FakeOpenAIClient(run_states=[], existing_assistants=existing)
    aid = _resolve_assistant(fake, mode="fast", model="gpt-5-mini")
    assert aid == "asst_existing_fast"
    # Must NOT have created a new one.
    assert fake.create_calls == []


def test_resolve_assistant_creates_when_missing():
    from backend.services.trade_thesis_foundry import _resolve_assistant

    fake = _FakeOpenAIClient(run_states=[], existing_assistants=[])
    aid = _resolve_assistant(fake, mode="deep", model="gpt-5")
    assert aid == "asst_macro-oil-thesis-deep"
    assert len(fake.create_calls) == 1
    call = fake.create_calls[0]
    assert call["model"] == "gpt-5"
    assert call["name"] == "macro-oil-thesis-deep"
    # Schema is registered as response_format.
    assert call["response_format"]["type"] == "json_schema"
    # Function tools registered.
    fn_names = {
        t["function"]["name"]
        for t in call["tools"]
        if t.get("type") == "function"
    }
    assert "run_cointegration" in fn_names
    assert "get_current_spread" in fn_names
    # Code interpreter registered.
    assert any(t.get("type") == "code_interpreter" for t in call["tools"])


# ---------------------------------------------------------------------------
# 7) Happy path — full thread/message/run flow + JSON parse
# ---------------------------------------------------------------------------
def test_generate_thesis_foundry_happy_path(sample_ctx, monkeypatch):
    from backend.services import trade_thesis_foundry as ftt

    payload = _make_canonical_thesis_payload()
    fake = _FakeOpenAIClient(
        run_states=[
            _run_state("queued"),
            _run_state("in_progress"),
            _run_state("completed"),
        ],
        assistant_text=json.dumps(payload),
        existing_assistants=[],
    )
    monkeypatch.setattr(ftt, "_make_openai_client", lambda: fake)
    # Tighten the poll interval so the test isn't laggy.
    th = ftt.generate_thesis_foundry(
        sample_ctx, log=False, mode="fast", poll_interval_s=0.0
    )
    # Source label tags Foundry routing.
    assert th.source.startswith("Foundry:")
    # Schema-mandatory fields present after guardrails.
    assert th.raw["stance"] in ("long_spread", "short_spread", "flat")
    assert "thesis_summary" in th.raw
    assert th.raw["disclaimer_shown"] is True
    # Plain-English headline survived (we passed a non-empty one).
    assert th.plain_english_headline
    # The user message was posted.
    assert len(fake.user_messages) == 1
    assert "context" in fake.user_messages[0]
    # Assistant was created (no existing list).
    assert len(fake.create_calls) == 1


# ---------------------------------------------------------------------------
# 8) Tool dispatch on requires_action
# ---------------------------------------------------------------------------
def test_generate_thesis_foundry_dispatches_function_tool(sample_ctx, monkeypatch):
    from backend.services import trade_thesis_foundry as ftt

    # Patch the tool implementation in the dispatch table so we don't
    # touch live providers.
    captured: dict[str, Any] = {}

    def _fake_run_coint(window_days: int = 252, **_kw: Any) -> dict:
        captured["window_days"] = window_days
        return {"window_days": window_days, "p_value": 0.012, "verdict": "cointegrated"}

    monkeypatch.setitem(ftt._TOOL_DISPATCH, "run_cointegration", _fake_run_coint)

    payload = _make_canonical_thesis_payload()
    fake = _FakeOpenAIClient(
        run_states=[
            _run_state("queued"),
            _run_state(
                "requires_action",
                required_action=_required_action(
                    "run_cointegration", {"window_days": 90}
                ),
            ),
            # After submit_tool_outputs returns, we step through to completion.
            _run_state("in_progress"),
            _run_state("completed"),
        ],
        assistant_text=json.dumps(payload),
        existing_assistants=[],
    )
    monkeypatch.setattr(ftt, "_make_openai_client", lambda: fake)

    th = ftt.generate_thesis_foundry(
        sample_ctx, log=False, mode="fast", poll_interval_s=0.0
    )
    assert th.source.startswith("Foundry:")
    # Tool was dispatched with the agent-supplied args.
    assert captured.get("window_days") == 90
    # Tool output was submitted back into the run.
    assert len(fake.tool_outputs_submitted) == 1
    submitted = fake.tool_outputs_submitted[0]
    assert submitted["tool_call_id"] == "call_001"
    body = json.loads(submitted["output"])
    assert body["verdict"] == "cointegrated"


# ---------------------------------------------------------------------------
# 9) Run failed → FoundryRunError
# ---------------------------------------------------------------------------
def test_generate_thesis_foundry_raises_on_run_failed(sample_ctx, monkeypatch):
    from backend.services import trade_thesis_foundry as ftt

    fake = _FakeOpenAIClient(
        run_states=[
            _run_state("queued"),
            _run_state(
                "failed",
                last_error=_FakeAttr(message="rate_limited"),
            ),
        ],
        assistant_text="{}",
        existing_assistants=[],
    )
    monkeypatch.setattr(ftt, "_make_openai_client", lambda: fake)
    with pytest.raises(ftt.FoundryRunError) as excinfo:
        ftt.generate_thesis_foundry(
            sample_ctx, log=False, mode="fast", poll_interval_s=0.0
        )
    msg = str(excinfo.value)
    assert "failed" in msg
    assert "rate_limited" in msg


def test_generate_thesis_foundry_raises_on_non_json_assistant_text(sample_ctx, monkeypatch):
    """Even on a `completed` run, a non-JSON assistant message must raise."""
    from backend.services import trade_thesis_foundry as ftt

    fake = _FakeOpenAIClient(
        run_states=[_run_state("completed")],
        assistant_text="this is not JSON",
        existing_assistants=[],
    )
    monkeypatch.setattr(ftt, "_make_openai_client", lambda: fake)
    with pytest.raises(ftt.FoundryRunError):
        ftt.generate_thesis_foundry(
            sample_ctx, log=False, mode="fast", poll_interval_s=0.0
        )


# ---------------------------------------------------------------------------
# 10) USE_FOUNDRY routing — flag flips the dispatch in trade_thesis.generate_thesis
# ---------------------------------------------------------------------------
def test_use_foundry_flag_routes_to_foundry_path(sample_ctx, monkeypatch):
    """When USE_FOUNDRY=true, ``generate_thesis`` must delegate to the Foundry path."""
    import trade_thesis
    from backend.services import trade_thesis_foundry as ftt

    monkeypatch.setenv("USE_FOUNDRY", "true")

    called: dict[str, Any] = {}

    def _fake_foundry(ctx, *, log=True, mode="fast", stream_handler=None):
        called["ctx"] = ctx
        called["mode"] = mode
        called["log"] = log
        # Return a minimal Thesis-like that satisfies the signature.
        return trade_thesis.Thesis(
            raw={"stance": "flat"},
            generated_at="2026-04-26T00:00:00Z",
            source="Foundry: gpt-5-mini",
            model="gpt-5-mini",
        )

    monkeypatch.setattr(ftt, "generate_thesis_foundry", _fake_foundry)

    th = trade_thesis.generate_thesis(sample_ctx, log=False, mode="fast")
    assert called.get("mode") == "fast"
    assert called.get("log") is False
    assert th.source.startswith("Foundry:")


def test_use_foundry_unset_routes_to_aoai_path(sample_ctx, monkeypatch):
    """When USE_FOUNDRY is unset, ``generate_thesis`` must take the legacy path."""
    import trade_thesis

    monkeypatch.delenv("USE_FOUNDRY", raising=False)
    th = trade_thesis.generate_thesis(sample_ctx, log=False, mode="fast")
    # No AOAI env vars set in unit tests → rule-based fallback.
    assert th.mode == "rule-based"
    assert th.source.startswith("rule-based")


def test_use_foundry_false_routes_to_aoai_path(sample_ctx, monkeypatch):
    import trade_thesis

    monkeypatch.setenv("USE_FOUNDRY", "false")
    th = trade_thesis.generate_thesis(sample_ctx, log=False, mode="fast")
    assert th.mode == "rule-based"


# ---------------------------------------------------------------------------
# Mode/deployment resolution
# ---------------------------------------------------------------------------
def test_foundry_deployment_for_defaults_and_overrides(monkeypatch):
    from backend.services.trade_thesis_foundry import _foundry_deployment_for

    # Defaults
    assert _foundry_deployment_for("fast") == "gpt-5-mini"
    assert _foundry_deployment_for("deep") == "gpt-5"
    assert _foundry_deployment_for("legacy") == "gpt-5-mini"

    monkeypatch.setenv("AZURE_AI_FOUNDRY_AGENT_MODEL_FAST", "fast-custom")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_AGENT_MODEL_DEEP", "deep-custom")
    assert _foundry_deployment_for("fast") == "fast-custom"
    assert _foundry_deployment_for("deep") == "deep-custom"


# ---------------------------------------------------------------------------
# 11) Integration smoke — only when RUN_FOUNDRY_SMOKE=1
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    os.environ.get("RUN_FOUNDRY_SMOKE") != "1",
    reason="Live Foundry smoke test gated by RUN_FOUNDRY_SMOKE=1",
)
def test_live_foundry_smoke_fast_mode(sample_ctx):
    """Hit the real Foundry endpoint and assert a schema-valid thesis comes back.

    Skipped by default. Set ``RUN_FOUNDRY_SMOKE=1`` and ensure a valid
    ``AZURE_AI_FOUNDRY_PROJECT_ENDPOINT`` is in the environment along
    with az login / managed-identity credentials.
    """
    from backend.services.trade_thesis_foundry import generate_thesis_foundry

    th = generate_thesis_foundry(sample_ctx, log=False, mode="fast")
    assert th.source.startswith("Foundry:")
    assert th.raw["stance"] in ("long_spread", "short_spread", "flat")
    assert isinstance(th.raw.get("thesis_summary"), str)
    assert th.raw["disclaimer_shown"] is True
