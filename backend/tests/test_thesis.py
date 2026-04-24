"""Tests for the /api/thesis/* routes.

We avoid calling into Azure OpenAI by monkey-patching the compat shim.
The tests exercise the SSE bridge itself (progress → deltas → done),
plus the latest/history readers and Pydantic validation.
"""

from __future__ import annotations

import json
import types
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import _compat, thesis_service


# ---------------------------------------------------------------------------
# Fake Thesis dataclass + fake generate_thesis that pumps deltas and returns.
# ---------------------------------------------------------------------------
@dataclass
class _FakeThesis:
    raw: dict = field(default_factory=lambda: {"stance": "long_spread", "conviction_0_to_10": 7.0})
    generated_at: str = "2026-04-23T10:00:00Z"
    source: str = "test (stub)"
    model: str = "gpt-test"
    plain_english_headline: str = "Brent is expensive vs WTI."
    context_fingerprint: str = "fp_test_0001"
    guardrails_applied: list = field(default_factory=lambda: ["clamp_conviction"])
    mode: str = "fast"
    latency_s: float = 0.05
    streamed: bool = True
    retried: bool = False
    instruments: list = field(default_factory=list)
    checklist: list = field(default_factory=list)


def _fake_generate_thesis(ctx, *, mode, stream_handler, log):
    """Stub that emits 3 token deltas synchronously then returns a _FakeThesis."""
    assert mode in ("fast", "deep")
    # generate_thesis runs on a worker thread; stream_handler marshals back.
    for chunk in ("Brent ", "is ", "expensive."):
        if stream_handler is not None:
            stream_handler(chunk)
    return _FakeThesis()


@pytest.fixture
def patched_compat(monkeypatch: pytest.MonkeyPatch):
    """Stub out the LLM call + context builder so tests don't hit Azure."""
    monkeypatch.setattr(_compat, "generate_thesis", _fake_generate_thesis)
    monkeypatch.setattr(_compat, "build_thesis_context", lambda: types.SimpleNamespace())
    yield


# ---------------------------------------------------------------------------
# SSE generate — happy path
# ---------------------------------------------------------------------------
def _parse_sse_events(raw: str) -> list[dict]:
    """Very small SSE line parser — enough to verify event/data pairs."""
    events: list[dict] = []
    current: dict = {}
    for line in raw.splitlines():
        if not line.strip():
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith(":"):
            # comment / heartbeat — skip
            continue
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current.setdefault("data", "")
            current["data"] += line.split(":", 1)[1].strip()
    if current:
        events.append(current)
    return events


def test_thesis_generate_sse_happy_path(patched_compat):
    """POST /api/thesis/generate streams progress, deltas, and a done event."""
    client = TestClient(create_app())
    with client.stream(
        "POST",
        "/api/thesis/generate",
        json={"mode": "fast", "portfolio_usd": 100_000},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = "".join(resp.iter_text())

    events = _parse_sse_events(body)
    kinds = [e.get("event") for e in events]

    # Must see at least one of each stage.
    assert "progress" in kinds, f"no progress events: {kinds}"
    assert "delta" in kinds, f"no delta events: {kinds}"
    assert "done" in kinds, f"no done event: {kinds}"

    # All 3 token chunks arrive as individual delta events.
    deltas = [json.loads(e["data"]) for e in events if e.get("event") == "delta"]
    assert [d["text"] for d in deltas] == ["Brent ", "is ", "expensive."]

    # Done payload carries the thesis + guardrails.
    done = next(e for e in events if e.get("event") == "done")
    payload = json.loads(done["data"])
    assert "thesis" in payload
    assert payload["applied_guardrails"] == ["clamp_conviction"]
    assert payload["materiality_flat"] is False


def test_thesis_regenerate_sse_same_shape(patched_compat):
    """POST /api/thesis/regenerate behaves identically — force=True flag."""
    client = TestClient(create_app())
    with client.stream(
        "POST",
        "/api/thesis/regenerate",
        json={"mode": "deep", "portfolio_usd": 250_000},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    events = _parse_sse_events(body)
    assert any(e.get("event") == "done" for e in events)


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------
def test_thesis_generate_rejects_invalid_mode():
    """Invalid ``mode`` value → 422 from pydantic, not a stream."""
    client = TestClient(create_app())
    resp = client.post(
        "/api/thesis/generate", json={"mode": "medium", "portfolio_usd": 1000}
    )
    assert resp.status_code == 422


def test_thesis_generate_rejects_nonpositive_portfolio():
    """Zero / negative portfolio → 422."""
    client = TestClient(create_app())
    resp = client.post(
        "/api/thesis/generate", json={"mode": "fast", "portfolio_usd": 0}
    )
    assert resp.status_code == 422


def test_thesis_generate_rejects_missing_portfolio():
    """``portfolio_usd`` is required."""
    client = TestClient(create_app())
    resp = client.post("/api/thesis/generate", json={"mode": "fast"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /latest and /history
# ---------------------------------------------------------------------------
def test_thesis_latest_empty(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Missing JSONL file → {thesis: None, empty: True}."""
    # Point the compat shim at a guaranteed-missing file.
    missing = tmp_path / "nope.jsonl"
    monkeypatch.setattr(_compat, "read_recent_theses", lambda n=10: [])
    client = TestClient(create_app())
    resp = client.get("/api/thesis/latest")
    assert resp.status_code == 200
    assert resp.json() == {"thesis": None, "empty": True}


def test_thesis_latest_returns_newest(monkeypatch: pytest.MonkeyPatch):
    """The router surfaces the first record from read_recent_theses."""
    record = {
        "timestamp": "2026-04-23T10:00:00Z",
        "source": "test",
        "model": "gpt-test",
        "context_fingerprint": "fp_xxx",
        "thesis": {"stance": "flat", "conviction_0_to_10": 5.0},
        "guardrails": [],
    }
    monkeypatch.setattr(_compat, "read_recent_theses", lambda n=10: [record])
    client = TestClient(create_app())
    resp = client.get("/api/thesis/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["empty"] is False
    assert body["thesis"] == record


def test_thesis_history_respects_limit(monkeypatch: pytest.MonkeyPatch):
    """GET /api/thesis/history?limit=N returns up to N rows and the count."""
    rows = [{"timestamp": f"2026-04-{23 - i:02d}T10:00:00Z", "thesis": {"stance": "flat"}} for i in range(5)]

    def _fake(n=10):
        return rows[:n]

    monkeypatch.setattr(_compat, "read_recent_theses", _fake)
    client = TestClient(create_app())
    resp = client.get("/api/thesis/history?limit=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    assert len(body["theses"]) == 3


def test_thesis_history_default_limit_30(monkeypatch: pytest.MonkeyPatch):
    """Default limit is 30 when the query param is omitted."""
    captured: dict[str, int] = {}

    def _fake(n=10):
        captured["n"] = n
        return []

    monkeypatch.setattr(_compat, "read_recent_theses", _fake)
    client = TestClient(create_app())
    resp = client.get("/api/thesis/history")
    assert resp.status_code == 200
    assert captured["n"] == 30


def test_thesis_history_rejects_bad_limit():
    """limit=0 or limit>500 → 422."""
    client = TestClient(create_app())
    resp = client.get("/api/thesis/history?limit=0")
    assert resp.status_code == 422
    resp = client.get("/api/thesis/history?limit=9999")
    assert resp.status_code == 422
