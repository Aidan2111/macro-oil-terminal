"""Unit tests for the observability shim (no-op when AI not configured)."""

from __future__ import annotations


def test_configure_returns_false_without_env(monkeypatch):
    import importlib, observability
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    importlib.reload(observability)  # reset module-level state
    assert observability.configure() is False


def test_span_is_safe_noop():
    import importlib, observability
    importlib.reload(observability)
    # Must not raise when AI isn't configured
    with observability.span("test_span", foo="bar", n=3) as s:
        pass


def test_trace_event_is_safe_noop():
    import importlib, observability
    importlib.reload(observability)
    # Arbitrary payload, including non-primitive attributes
    observability.trace_event("ev", foo="bar", obj=object())


def test_configure_idempotent(monkeypatch):
    import importlib, observability
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    importlib.reload(observability)
    assert observability.configure() is False
    # Second call returns the cached result
    assert observability.configure() is False
