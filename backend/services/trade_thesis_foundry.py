"""Azure AI Foundry Agent Service implementation of ``generate_thesis``.

This module is the Foundry-backed sibling of ``trade_thesis.generate_thesis``.
It wraps :class:`azure.ai.projects.AIProjectClient` (via its embedded OpenAI
Assistants client) to drive a tool-calling agent loop:

  1.  Authenticate with ``DefaultAzureCredential`` against the Foundry
      project endpoint pinned via ``AZURE_AI_FOUNDRY_PROJECT_ENDPOINT``
      (or the legacy ``AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING``).
  2.  Resolve / create a persistent Assistant on the requested model
      deployment (``gpt-5`` for ``mode=deep``, ``gpt-5-mini`` for fast).
      The assistant is registered with six function tools — spread,
      inventory, CFTC, fleet, cointegration, backtest — and the
      built-in ``code_interpreter`` for ad-hoc scenario maths.
  3.  Open a thread, post the structured ``ThesisContext`` as a
      pre-rendered system briefing message, then create a run.
  4.  Poll the run, dispatching ``requires_action`` events back to
      the Python tool implementations (which in turn delegate to the
      existing live-data services). Submit each tool's JSON output
      back into the run.
  5.  When the run reaches ``completed``, pull the assistant's last
      message and parse it as JSON conforming to ``THESIS_JSON_SCHEMA``.
  6.  Fold the parsed payload + run metadata into a ``Thesis`` dataclass
      identical in shape to the AOAI path so the FastAPI/SSE bridge,
      the Pydantic envelope, and the React frontend remain unaware of
      which generator served the request.

If any step errors, we **raise** — there is no silent rule-based
fallback in the Foundry path. The non-Foundry route in
``trade_thesis.generate_thesis`` is selected by the ``USE_FOUNDRY``
feature flag, not by exception handling. That keeps SRE behaviour
crisp: a Foundry outage surfaces as the FastAPI ``503`` envelope,
the operator flips ``USE_FOUNDRY=false`` in App Settings, and the
existing AOAI path takes over within one redeploy.

Reference: ``docs/designs/foundry-migration.md``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import _compat  # noqa: F401 — sets sys.path for legacy imports

# Import the data-shape and shared constants from the existing module.
# We do NOT re-implement the schema — it's the single source of truth.
import trade_thesis  # type: ignore  # noqa: E402  (legacy top-level)
from trade_thesis import (  # type: ignore  # noqa: E402
    SYSTEM_PROMPT,
    THESIS_JSON_SCHEMA,
    Thesis,
    ThesisContext,
    _apply_guardrails,
    _append_audit,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class FoundryConfigError(RuntimeError):
    """Raised when required Foundry env vars / settings are missing."""


class FoundryRunError(RuntimeError):
    """Raised when a Foundry agent run terminates without a usable thesis.

    Carries the run's terminal status + any ``last_error`` payload so the
    FastAPI 503 detail string is helpful for the operator.
    """


# ---------------------------------------------------------------------------
# Mode → deployment resolution
# ---------------------------------------------------------------------------
_VALID_MODES = ("fast", "deep", "legacy")


def _foundry_deployment_for(mode: str) -> str:
    """Resolve the Foundry model deployment for a mode.

    Env precedence (mirrors ``trade_thesis._deployment_for`` but reads
    Foundry-scoped vars so AOAI deployments aren't accidentally used):

      fast → AZURE_AI_FOUNDRY_AGENT_MODEL_FAST → "gpt-5-mini"
      deep → AZURE_AI_FOUNDRY_AGENT_MODEL_DEEP → "gpt-5"
      legacy → AZURE_AI_FOUNDRY_AGENT_MODEL_FAST → "gpt-5-mini"
    """
    fast = os.environ.get("AZURE_AI_FOUNDRY_AGENT_MODEL_FAST", "gpt-5-mini")
    if mode == "deep":
        return os.environ.get("AZURE_AI_FOUNDRY_AGENT_MODEL_DEEP", "gpt-5")
    return fast


# ---------------------------------------------------------------------------
# Function-tool implementations — thin adapters over existing services.
#
# Each tool's JSON shape is contract: the agent reads the docstring (via
# the registered tool definition below) and emits ``submit_tool_outputs``
# payloads that we route here. The return values must be JSON-serialisable
# dicts; the dispatch wrapper does the json.dumps step.
# ---------------------------------------------------------------------------

def _tool_get_current_spread(*_args: Any, **_kwargs: Any) -> dict:
    """Return the current Brent-WTI spread state via spread_service."""
    from . import spread_service

    resp = spread_service.get_spread_response(history_bars=1)
    payload = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
    # Drop heavy time-series; the assistant only needs the latest state.
    payload.pop("history", None)
    return payload


def _tool_get_inventory_state(*_args: Any, **_kwargs: Any) -> dict:
    """Return EIA/FRED inventory state via inventory_service."""
    from . import inventory_service

    resp = inventory_service.get_inventory_response()
    payload = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
    payload.pop("history", None)
    return payload


def _tool_get_cftc_positioning(*_args: Any, **_kwargs: Any) -> dict:
    """Return CFTC managed-money positioning via cftc_service."""
    from . import cftc_service

    resp = cftc_service.get_cftc_response()
    payload = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
    return payload


def _tool_get_fleet_summary(*_args: Any, **_kwargs: Any) -> dict:
    """Return AISStream fleet summary via fleet_service."""
    from . import fleet_service

    cats = fleet_service.get_categories()
    snap = fleet_service.get_snapshot()
    return {
        "categories": cats,
        "vessel_count": len(snap),
    }


def _tool_run_cointegration(window_days: int = 252, **_kwargs: Any) -> dict:
    """Run Engle-Granger cointegration on the last ``window_days`` Brent/WTI."""
    from cointegration import engle_granger  # type: ignore
    from providers import pricing as pricing_provider  # type: ignore

    pr = pricing_provider.fetch_pricing_daily()
    df = pr.frame.tail(int(window_days))
    result = engle_granger(df["Brent"], df["WTI"])
    return {
        "window_days": int(window_days),
        "p_value": float(result.p_value) if result.p_value == result.p_value else None,
        "verdict": str(result.verdict),
        "is_cointegrated": bool(result.is_cointegrated),
        "hedge_ratio": (
            float(result.hedge_ratio) if result.hedge_ratio == result.hedge_ratio else None
        ),
        "half_life_days": (
            float(result.half_life_days)
            if result.half_life_days is not None
            and result.half_life_days == result.half_life_days
            else None
        ),
    }


def _tool_run_backtest_window(start: str, end: str, **_kwargs: Any) -> dict:
    """Run the mean-reversion backtest over [start, end] (ISO YYYY-MM-DD)."""
    from . import backtest_service

    resp = backtest_service.run_backtest(
        entry_z=2.0, exit_z=0.5, lookback=90, start=start, end=end
    )
    payload = resp.model_dump() if hasattr(resp, "model_dump") else resp.dict()
    # Trades+equity curve are heavy; the agent only needs aggregates.
    payload.pop("trades", None)
    payload.pop("equity_curve", None)
    return payload


# Dispatch table — name → callable.
#
# Tests can monkey-patch entries here to assert the dispatch envelope
# without pulling the live providers in.
_TOOL_DISPATCH: dict[str, Callable[..., dict]] = {
    "get_current_spread": _tool_get_current_spread,
    "get_inventory_state": _tool_get_inventory_state,
    "get_cftc_positioning": _tool_get_cftc_positioning,
    "get_fleet_summary": _tool_get_fleet_summary,
    "run_cointegration": _tool_run_cointegration,
    "run_backtest_window": _tool_run_backtest_window,
}


# ---------------------------------------------------------------------------
# Tool definitions (registered with the assistant at create-time).
#
# Each ``tools`` entry must be JSON-serialisable; the OpenAI Assistants
# wire format is `{"type": "function", "function": {...}}` plus the
# special-case `{"type": "code_interpreter"}` envelope.
# ---------------------------------------------------------------------------
def _build_tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_current_spread",
                "description": (
                    "Return the latest Brent / WTI / Brent-WTI spread, the 90-day "
                    "rolling Z, and the human-readable stretch label."
                ),
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_inventory_state",
                "description": (
                    "Return current US crude inventory, 4w/52w slope, projected "
                    "depletion floor date, and source provenance (EIA / FRED)."
                ),
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_cftc_positioning",
                "description": (
                    "Return CFTC Commitments-of-Traders WTI positioning: open "
                    "interest, managed-money / producer / swap-dealer net, and "
                    "the 3-year Z-score / percentile of the MM net position."
                ),
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_fleet_summary",
                "description": (
                    "Return the AISStream live tanker fleet summary: counts by "
                    "category (Jones Act / shadow fleet / sanctioned / regular)."
                ),
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_cointegration",
                "description": (
                    "Run an Engle-Granger cointegration test on Brent and WTI "
                    "over the last `window_days` daily closes. Returns the "
                    "p-value, verdict, hedge ratio, and implied half-life."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "window_days": {
                            "type": "integer",
                            "description": "Lookback window in trading days (default 252).",
                            "minimum": 30,
                            "maximum": 2520,
                        }
                    },
                    "required": ["window_days"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_backtest_window",
                "description": (
                    "Run the mean-reversion backtest over a custom date "
                    "window. Returns aggregate stats (Sharpe, hit rate, "
                    "max drawdown, n trades) without the trade-by-trade log."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start": {
                            "type": "string",
                            "description": "Inclusive start date, YYYY-MM-DD.",
                        },
                        "end": {
                            "type": "string",
                            "description": "Inclusive end date, YYYY-MM-DD.",
                        },
                    },
                    "required": ["start", "end"],
                },
            },
        },
        # Code interpreter for ad-hoc scenario math.
        {"type": "code_interpreter"},
    ]


# ---------------------------------------------------------------------------
# Project / OpenAI-client construction.
#
# Split into helpers so unit tests can patch the seam (a fake OpenAI
# client is injected via ``_make_openai_client``) without touching
# Azure SDK internals.
# ---------------------------------------------------------------------------
def _project_endpoint() -> str:
    """Return the Foundry project endpoint, raising FoundryConfigError if unset.

    ``AZURE_AI_FOUNDRY_PROJECT_ENDPOINT`` is the canonical name in
    azure-ai-projects 2.x. We also accept the legacy 1.x name
    ``AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING`` for backwards
    compatibility with the original design doc.
    """
    endpoint = (
        os.environ.get("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")
        or os.environ.get("AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING")
    )
    if not endpoint:
        raise FoundryConfigError(
            "AZURE_AI_FOUNDRY_PROJECT_ENDPOINT is not set; cannot reach the "
            "Azure AI Foundry project. Set the env var (or flip USE_FOUNDRY=false)."
        )
    return endpoint


def _make_openai_client():  # noqa: ANN202
    """Construct an Azure OpenAI client for the Assistants API.

    Tests monkey-patch this function to inject a fake.

    The Foundry project's ``/openai/v1`` proxy surface does **not**
    support the Assistants (beta.threads / beta.assistants) endpoints.
    We therefore target the Azure OpenAI resource directly via
    ``AZURE_OPENAI_ENDPOINT``, using ``DefaultAzureCredential`` for
    Entra ID token auth (the App Service managed identity already has
    ``Cognitive Services OpenAI User`` on the resource).

    Falls back to API-key auth via ``AZURE_OPENAI_KEY`` when the
    managed-identity path is not available (local dev).
    """
    from openai import AzureOpenAI
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        raise FoundryConfigError(
            "AZURE_OPENAI_ENDPOINT is not set; the Foundry Assistants path "
            "needs the Azure OpenAI resource endpoint directly."
        )

    api_version = os.environ.get(
        "AZURE_OPENAI_ASSISTANTS_API_VERSION", "2025-03-01-preview"
    )
    api_key = os.environ.get("AZURE_OPENAI_KEY")

    if api_key:
        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    return AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=api_version,
    )


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------
_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "expired", "incomplete"}
# gpt-5 cold-start + function-tool round-trip can easily exceed 90s. Two
# production retries (USE_FOUNDRY=true on 2026-04-26) elapsed 70-95s and
# both tripped the previous 90s deadline, raising FoundryRunError just as
# the assistant's text was about to land. Bumping to 240s gives generous
# margin while still bounding pathological hangs. The SSE bridge in
# thesis_service.py wraps `await runner_task` in try/except so a deadline
# trip emits event:error rather than truncating the stream.
_DEFAULT_RUN_DEADLINE_S = 240.0
_DEFAULT_POLL_INTERVAL_S = 0.6


def _dispatch_tool_call(name: str, args_raw: str) -> dict:
    """Look up ``name`` in the dispatch table, parse JSON args, invoke."""
    fn = _TOOL_DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown_tool:{name}"}
    try:
        args = json.loads(args_raw or "{}")
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        args = {}
    try:
        return fn(**args)
    except Exception as exc:  # pragma: no cover — exercised via mocks
        logger.exception("tool %s raised", name)
        return {"error": f"{type(exc).__name__}: {exc}"}


def _serialise_message_content(message_obj: Any) -> str:
    """Pull the text portion out of an Assistants message envelope.

    The Assistants SDK returns ``message.content`` as a list of
    ``MessageContent`` parts; for our JSON-schema-shaped agent the
    completion is a single ``text`` part. We concatenate any text
    parts defensively.
    """
    parts = getattr(message_obj, "content", None) or []
    chunks: list[str] = []
    for part in parts:
        # SDK objects expose `.text.value` (`Text` part); plain dicts
        # mirror that under content[i]["text"]["value"].
        if hasattr(part, "text") and getattr(part, "text", None) is not None:
            value = getattr(part.text, "value", None)
            if value is not None:
                chunks.append(str(value))
                continue
        if isinstance(part, dict):
            text = part.get("text") or {}
            value = text.get("value") if isinstance(text, dict) else None
            if value is not None:
                chunks.append(str(value))
    return "".join(chunks)


def _build_user_briefing(ctx: ThesisContext, mode: str) -> str:
    """Render a user-message payload that mirrors the AOAI path's content."""
    payload = {
        "note": (
            "All fields are real current values. Produce a trade thesis that "
            "cites them explicitly. You have function tools available to "
            "fetch fresher live state (spread / inventory / CFTC / fleet) "
            "and to run cointegration and backtests; call them when the "
            "context below is insufficient or when you want to confirm a "
            "structural claim. The final assistant message MUST be a single "
            "JSON object matching the trade_thesis schema — no code fences, "
            "no commentary."
        ),
        "mode_hint": mode,
        "context": ctx.to_dict(),
    }
    return json.dumps(payload, default=str)


def _resolve_assistant(client: Any, *, mode: str, model: str) -> str:
    """Return the assistant_id, creating the agent on first use.

    Idempotency: we list assistants and reuse one whose ``name`` matches
    ``macro-oil-thesis-{mode}``. If none exists we create it.
    """
    target_name = f"macro-oil-thesis-{mode}"
    try:
        listing = client.beta.assistants.list(limit=100)
        candidates = list(getattr(listing, "data", []) or [])
        for a in candidates:
            if getattr(a, "name", None) == target_name:
                return getattr(a, "id")
    except Exception as exc:  # pragma: no cover — defensive
        logger.info("assistant listing failed (%r); attempting create", exc)

    created = client.beta.assistants.create(
        model=model,
        name=target_name,
        instructions=SYSTEM_PROMPT,
        tools=_build_tool_specs(),
        response_format={"type": "json_schema", "json_schema": THESIS_JSON_SCHEMA},
    )
    return getattr(created, "id")


def _run_agent(
    client: Any,
    *,
    assistant_id: str,
    user_message: str,
    deadline_s: float,
    poll_interval_s: float,
) -> tuple[str, dict]:
    """Drive the thread+run+tool-dispatch loop. Return (assistant_text, meta)."""
    t0 = time.monotonic()

    thread = client.beta.threads.create()
    thread_id = getattr(thread, "id")

    client.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=user_message
    )

    run = client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=assistant_id
    )
    run_id = getattr(run, "id")

    tool_calls_made: list[str] = []

    while True:
        if time.monotonic() - t0 > deadline_s:
            raise FoundryRunError(
                f"Foundry run exceeded deadline of {deadline_s:.0f}s "
                f"(thread={thread_id}, run={run_id})"
            )

        status = getattr(run, "status", None)

        if status == "requires_action":
            ra = getattr(run, "required_action", None)
            sto = getattr(ra, "submit_tool_outputs", None) if ra is not None else None
            calls = getattr(sto, "tool_calls", None) if sto is not None else None
            outputs: list[dict] = []
            for call in calls or []:
                fn = getattr(call, "function", None)
                name = getattr(fn, "name", None) if fn is not None else None
                args_raw = getattr(fn, "arguments", "") if fn is not None else ""
                tool_calls_made.append(name or "?")
                result = _dispatch_tool_call(name or "", args_raw or "")
                outputs.append(
                    {
                        "tool_call_id": getattr(call, "id"),
                        "output": json.dumps(result, default=str),
                    }
                )
            run = client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id, run_id=run_id, tool_outputs=outputs
            )
            continue

        if status in _TERMINAL_STATUSES:
            break

        time.sleep(poll_interval_s)
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)

    if getattr(run, "status", None) != "completed":
        last_err = getattr(run, "last_error", None)
        err_msg = ""
        if last_err is not None:
            err_msg = (
                getattr(last_err, "message", None)
                or (last_err.get("message") if isinstance(last_err, dict) else None)
                or ""
            )
        raise FoundryRunError(
            f"Foundry run terminated with status="
            f"{getattr(run, 'status', '?')!s}; last_error={err_msg!s}"
        )

    msgs = client.beta.threads.messages.list(
        thread_id=thread_id, order="desc", limit=10
    )
    data = list(getattr(msgs, "data", []) or [])
    assistant_msgs = [m for m in data if getattr(m, "role", None) == "assistant"]
    if not assistant_msgs:
        raise FoundryRunError("Foundry run completed but no assistant message returned.")
    text = _serialise_message_content(assistant_msgs[0])
    if not text.strip():
        raise FoundryRunError(
            "Foundry run completed but assistant message text was empty."
        )

    meta = {
        "mode": None,  # filled by caller
        "deployment": None,  # filled by caller
        "is_reasoning": False,
        "streamed": False,
        "retried": False,
        "latency_s": round(time.monotonic() - t0, 2),
        "thread_id": thread_id,
        "run_id": run_id,
        "tool_calls": tool_calls_made,
        "assistant_id": assistant_id,
    }
    return text, meta


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def generate_thesis_foundry(
    ctx: ThesisContext,
    *,
    log: bool = True,
    mode: str = "fast",
    stream_handler: Optional[Callable[[str], None]] = None,
    deadline_s: float = _DEFAULT_RUN_DEADLINE_S,
    poll_interval_s: float = _DEFAULT_POLL_INTERVAL_S,
) -> Thesis:
    """Run the Foundry agent end-to-end and return a ``Thesis``.

    Mirrors :func:`trade_thesis.generate_thesis`'s signature so the
    feature-flag swap in ``trade_thesis.generate_thesis`` is a single
    delegating call. Unlike the AOAI path, this function **raises**
    on failure — there is no silent rule-based fallback. The
    ``USE_FOUNDRY`` flag in ``trade_thesis.generate_thesis`` controls
    routing; a Foundry outage is a 503 at the FastAPI layer.

    ``stream_handler`` is accepted for signature parity but the
    Foundry Assistants run-poll flow does not stream tokens. If the
    flag is provided we emit a single end-of-run delta carrying the
    full assistant text — this keeps the SSE bridge in
    ``thesis_service`` rendering progress correctly.
    """
    if mode not in _VALID_MODES:
        mode = "fast"

    deployment = _foundry_deployment_for(mode)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fingerprint = ctx.fingerprint()

    client = _make_openai_client()
    assistant_id = _resolve_assistant(client, mode=mode, model=deployment)
    user_message = _build_user_briefing(ctx, mode)

    text, meta = _run_agent(
        client,
        assistant_id=assistant_id,
        user_message=user_message,
        deadline_s=deadline_s,
        poll_interval_s=poll_interval_s,
    )
    meta["mode"] = mode
    meta["deployment"] = deployment

    # Emit the full body as a single delta so the SSE bridge stays well-fed
    # even though Foundry is poll-based.
    if stream_handler is not None:
        try:
            stream_handler(text)
        except Exception:  # pragma: no cover — defensive
            pass

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FoundryRunError(
            f"Foundry assistant returned non-JSON content "
            f"(run={meta.get('run_id')}): {exc}"
        ) from exc

    raw, notes = _apply_guardrails(raw, ctx)

    # Backstop the plain-English headline using the same template the AOAI
    # path uses. Reuses the helpers in ``language`` so wording stays in sync.
    headline = str(raw.get("plain_english_headline") or "").strip()
    if (not headline) or len(headline.split()) > 30:
        try:
            from language import describe_stance, describe_stretch  # type: ignore

            band = describe_stretch(
                abs(
                    float(
                        raw.get("entry", {}).get(
                            "suggested_z_level", ctx.current_z
                        )
                        or 0.0
                    )
                )
            )
            verb = describe_stance(str(raw.get("stance", "flat")))
            raw["plain_english_headline"] = (
                f"Brent vs WTI is at a {band.lower()} level; "
                f"the model suggests {verb.lower()}."
            )
        except Exception:
            raw["plain_english_headline"] = (
                "Brent vs WTI is within normal range; the model suggests wait."
            )

    thesis = Thesis(
        raw=raw,
        generated_at=generated_at,
        source=f"Foundry: {deployment}",
        model=deployment,
        plain_english_headline=str(raw.get("plain_english_headline") or ""),
        context_fingerprint=fingerprint,
        guardrails_applied=notes,
        mode=mode,
        latency_s=float(meta.get("latency_s", 0.0)),
        streamed=False,
        retried=False,
    )

    if log:
        try:
            _append_audit(ctx, thesis)
        except Exception:  # pragma: no cover — audit-log writes never fatal
            logger.debug("audit append failed", exc_info=True)

    return thesis


__all__ = [
    "FoundryConfigError",
    "FoundryRunError",
    "generate_thesis_foundry",
    "_TOOL_DISPATCH",
    "_build_tool_specs",
    "_foundry_deployment_for",
    "_resolve_assistant",
    "_run_agent",
    "_make_openai_client",
]
