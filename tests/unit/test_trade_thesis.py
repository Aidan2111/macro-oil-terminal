"""Unit tests for the trade_thesis module (offline — no live LLM)."""

from __future__ import annotations

import json

import pytest


def test_schema_required_keys():
    from trade_thesis import THESIS_JSON_SCHEMA
    required = set(THESIS_JSON_SCHEMA["schema"]["required"])
    assert {
        "stance", "conviction_0_to_10", "time_horizon_days",
        "entry", "exit", "position_sizing",
        "thesis_summary", "key_drivers", "invalidation_risks",
        "catalyst_watchlist", "data_caveats", "disclaimer_shown",
        "reasoning_summary",
    }.issubset(required)


def test_deployment_for_env_precedence(monkeypatch):
    from trade_thesis import _deployment_for
    # No env → default
    assert _deployment_for("fast") == "gpt-4o-mini"
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "legacy-dep")
    assert _deployment_for("legacy") == "legacy-dep"
    assert _deployment_for("fast") == "legacy-dep"
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4o")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_DEEP", "o4-mini")
    assert _deployment_for("fast") == "gpt-4o"
    assert _deployment_for("deep") == "o4-mini"
    # Unknown modes silently coerce to fast semantics downstream; _deployment_for
    # for an unknown mode is not meant to be called directly.


def test_rule_based_fallback_has_reasoning_summary(sample_ctx):
    from trade_thesis import _rule_based_fallback
    raw = _rule_based_fallback(sample_ctx)
    assert "reasoning_summary" in raw
    assert len(raw["reasoning_summary"]) > 0


def test_guardrail_inventory_missing_forces_flat(sample_ctx):
    from trade_thesis import _apply_guardrails, _rule_based_fallback
    ctx_missing = sample_ctx.__class__(**{**sample_ctx.__dict__, "inventory_source": "unavailable"})
    raw = _rule_based_fallback(ctx_missing)
    raw["stance"] = "long_spread"
    raw["conviction_0_to_10"] = 9.0
    out, notes = _apply_guardrails(raw, ctx_missing)
    assert out["stance"] == "flat"
    assert out["conviction_0_to_10"] <= 3


def test_guardrail_conviction_clamp_on_weak_backtest(sample_ctx):
    from trade_thesis import _apply_guardrails, _rule_based_fallback
    ctx_weak = sample_ctx.__class__(**{**sample_ctx.__dict__, "bt_hit_rate": 0.40})
    raw = _rule_based_fallback(ctx_weak)
    raw["conviction_0_to_10"] = 9.0
    out, notes = _apply_guardrails(raw, ctx_weak)
    assert out["conviction_0_to_10"] <= 5.0
    assert any("calibration" in n.lower() for n in notes)


def test_guardrail_sizing_cap_at_20(sample_ctx):
    from trade_thesis import _apply_guardrails, _rule_based_fallback
    raw = _rule_based_fallback(sample_ctx)
    raw["position_sizing"]["suggested_pct_of_capital"] = 35.0
    out, notes = _apply_guardrails(raw, sample_ctx)
    assert out["position_sizing"]["suggested_pct_of_capital"] == 20.0


def test_generate_no_env_uses_rule_based(sample_ctx):
    from trade_thesis import generate_thesis
    th = generate_thesis(sample_ctx, log=False)
    assert th.source.startswith("rule-based")
    assert th.raw.get("disclaimer_shown") is True
    assert th.mode == "rule-based"
    assert th.context_fingerprint


def test_fingerprint_stable(sample_ctx):
    fp1 = sample_ctx.fingerprint()
    # A no-op change to a field excluded from the fingerprint must not change it.
    ctx2 = sample_ctx.__class__(**{**sample_ctx.__dict__, "days_since_last_abs_z_over_2": 999})
    assert ctx2.fingerprint() == fp1
    # A meaningful change should flip it.
    ctx3 = sample_ctx.__class__(**{**sample_ctx.__dict__, "current_z": sample_ctx.current_z + 1.0})
    assert ctx3.fingerprint() != fp1


def test_materiality_fingerprint_keys(sample_ctx):
    from trade_thesis import _materiality_fingerprint
    fp = _materiality_fingerprint(sample_ctx)
    for k in ("z", "brent", "wti", "inv_4w_sign", "vol_bucket", "inv_latest"):
        assert k in fp


def test_materiality_first_run(sample_ctx):
    from trade_thesis import _materiality_fingerprint, context_changed_materially
    fp = _materiality_fingerprint(sample_ctx)
    assert context_changed_materially(None, fp) == ["first_run"]


def test_materiality_z_threshold(sample_ctx):
    from trade_thesis import _materiality_fingerprint, context_changed_materially
    prev = _materiality_fingerprint(sample_ctx)
    ctx2 = sample_ctx.__class__(**{**sample_ctx.__dict__, "current_z": sample_ctx.current_z + 0.5})
    cur = _materiality_fingerprint(ctx2)
    reasons = context_changed_materially(prev, cur)
    assert any("dislocation" in r.lower() for r in reasons)


def test_materiality_no_change(sample_ctx):
    from trade_thesis import _materiality_fingerprint, context_changed_materially
    prev = _materiality_fingerprint(sample_ctx)
    cur = dict(prev)
    assert context_changed_materially(prev, cur) == []


def test_materiality_vol_regime_flip(sample_ctx):
    from trade_thesis import _materiality_fingerprint, context_changed_materially
    prev_ctx = sample_ctx.__class__(**{**sample_ctx.__dict__, "vol_spread_1y_percentile": 10.0})
    cur_ctx = sample_ctx.__class__(**{**sample_ctx.__dict__, "vol_spread_1y_percentile": 80.0})
    prev = _materiality_fingerprint(prev_ctx)
    cur = _materiality_fingerprint(cur_ctx)
    reasons = context_changed_materially(prev, cur)
    assert any("vol regime" in r.lower() for r in reasons)


def test_diff_theses_stance_flip():
    from trade_thesis import diff_theses
    prev = {"stance": "long_spread", "conviction_0_to_10": 6, "invalidation_risks": [], "catalyst_watchlist": []}
    cur = {"stance": "short_spread", "conviction_0_to_10": 7, "invalidation_risks": [], "catalyst_watchlist": []}
    out = diff_theses(prev, cur)
    assert any("Stance flipped" in d for d in out)
    assert any("Confidence" in d for d in out)


def test_diff_theses_new_risk():
    from trade_thesis import diff_theses
    prev = {"stance": "flat", "conviction_0_to_10": 3, "invalidation_risks": ["alpha"], "catalyst_watchlist": []}
    cur = {"stance": "flat", "conviction_0_to_10": 3, "invalidation_risks": ["alpha", "beta"], "catalyst_watchlist": []}
    out = diff_theses(prev, cur)
    assert any("beta" in d for d in out)


def test_history_stats_empty():
    from trade_thesis import history_stats
    out = history_stats([])
    assert out["n"] == 0
    assert out["avg_conf"] == 0.0


def test_streaming_handler_receives_deltas(sample_ctx, monkeypatch):
    """Mock the AzureOpenAI client to exercise the streaming handler path."""
    import trade_thesis as tt

    class _Delta:
        def __init__(self, content): self.content = content
    class _Choice:
        def __init__(self, content): self.delta = _Delta(content)
    class _Event:
        def __init__(self, content): self.choices = [_Choice(content)]

    class _FakeStream:
        def __iter__(self):
            # Chunked valid JSON
            payload = {
                "stance": "flat",
                "conviction_0_to_10": 3.0,
                "time_horizon_days": 14,
                "entry": {"trigger_condition": "x", "suggested_z_level": 0.0, "suggested_spread_usd": 0.0},
                "exit": {"target_condition": "x", "target_z_level": 0.0, "stop_loss_condition": "x", "stop_z_level": 0.0},
                "position_sizing": {"method": "fixed_fractional", "suggested_pct_of_capital": 1.0, "rationale": "r"},
                "thesis_summary": "s",
                "key_drivers": ["d1"],
                "invalidation_risks": ["r1"],
                "catalyst_watchlist": [],
                "data_caveats": [],
                "disclaimer_shown": True,
                "reasoning_summary": "rs",
            }
            s = json.dumps(payload)
            for i in range(0, len(s), 16):
                yield _Event(s[i:i+16])

    class _Chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                return _FakeStream()
    class _FakeClient:
        def __init__(self, **kw): pass
        chat = _Chat

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://stub.example")
    monkeypatch.setenv("AZURE_OPENAI_KEY", "stub")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4o")

    import openai
    monkeypatch.setattr(openai, "AzureOpenAI", lambda **kw: _FakeClient(**kw))

    seen = []
    th = tt.generate_thesis(sample_ctx, mode="fast", stream_handler=lambda d: seen.append(d), log=False)
    assert seen, "streaming handler never received deltas"
    assert th.streamed is True
    assert th.raw["stance"] == "flat"
    assert th.raw["reasoning_summary"] == "rs"


def test_streaming_fallback_to_sync_on_error(sample_ctx, monkeypatch):
    """If streaming raises, we must retry sync and still produce a valid thesis."""
    import trade_thesis as tt

    calls = {"streamed": 0, "sync": 0}

    class _Response:
        def __init__(self, content):
            class _M: pass
            self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]

    payload = json.dumps({
        "stance": "flat", "conviction_0_to_10": 2.0, "time_horizon_days": 7,
        "entry": {"trigger_condition": "x", "suggested_z_level": 0.0, "suggested_spread_usd": 0.0},
        "exit": {"target_condition": "x", "target_z_level": 0.0, "stop_loss_condition": "x", "stop_z_level": 0.0},
        "position_sizing": {"method": "fixed_fractional", "suggested_pct_of_capital": 1.0, "rationale": "r"},
        "thesis_summary": "s", "key_drivers": ["d"], "invalidation_risks": ["r"],
        "catalyst_watchlist": [], "data_caveats": [], "disclaimer_shown": True,
        "reasoning_summary": "rs",
    })

    class _Chat:
        class completions:
            @staticmethod
            def create(**kw):
                if kw.get("stream"):
                    calls["streamed"] += 1
                    raise RuntimeError("stream boom")
                calls["sync"] += 1
                return _Response(payload)

    class _FakeClient:
        def __init__(self, **kw): pass
        chat = _Chat

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://stub.example")
    monkeypatch.setenv("AZURE_OPENAI_KEY", "stub")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4o")

    import openai
    monkeypatch.setattr(openai, "AzureOpenAI", lambda **kw: _FakeClient(**kw))

    th = tt.generate_thesis(sample_ctx, mode="fast", stream_handler=lambda d: None, log=False)
    assert calls["streamed"] == 1
    assert calls["sync"] == 1
    assert th.retried is True
    assert th.raw["stance"] == "flat"


def test_generate_thesis_malformed_json_retries(sample_ctx, monkeypatch):
    """If the first sync response is malformed JSON, we retry once with a nudge."""
    import trade_thesis as tt

    good = json.dumps({
        "stance": "flat", "conviction_0_to_10": 1.0, "time_horizon_days": 7,
        "entry": {"trigger_condition": "x", "suggested_z_level": 0.0, "suggested_spread_usd": 0.0},
        "exit": {"target_condition": "x", "target_z_level": 0.0, "stop_loss_condition": "x", "stop_z_level": 0.0},
        "position_sizing": {"method": "fixed_fractional", "suggested_pct_of_capital": 1.0, "rationale": "r"},
        "thesis_summary": "s", "key_drivers": ["d"], "invalidation_risks": ["r"],
        "catalyst_watchlist": [], "data_caveats": [], "disclaimer_shown": True, "reasoning_summary": "rs",
    })
    state = {"count": 0}

    class _Chat:
        class completions:
            @staticmethod
            def create(**kw):
                state["count"] += 1
                content = "not valid json at all" if state["count"] == 1 else good

                class _C:
                    message = type("M", (), {"content": content})
                return type("R", (), {"choices": [_C()]})

    class _FakeClient:
        def __init__(self, **kw): pass
        chat = _Chat

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://stub.example")
    monkeypatch.setenv("AZURE_OPENAI_KEY", "stub")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4o")

    import openai
    monkeypatch.setattr(openai, "AzureOpenAI", lambda **kw: _FakeClient(**kw))

    th = tt.generate_thesis(sample_ctx, mode="fast", stream_handler=None, log=False)
    assert state["count"] == 2
    assert th.retried is True
    assert th.raw["stance"] == "flat"
