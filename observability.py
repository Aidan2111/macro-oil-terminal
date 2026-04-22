"""Application Insights wire-up.

Defensive: if `APPLICATIONINSIGHTS_CONNECTION_STRING` isn't set (local dev)
or the Azure Monitor SDK isn't installed, every function here becomes a
no-op. Never raises.

Usage in ``app.py``::

    from observability import configure, trace_event, tracer

    configure()                          # once on module import
    with tracer().start_as_current_span("thesis.generate"):
        thesis = generate_thesis(ctx)
    trace_event("thesis_generated", stance=thesis.raw["stance"])
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager, nullcontext
from typing import Any

logger = logging.getLogger("observability")

_configured = False
_tracer = None


def configure() -> bool:
    """Configure Azure Monitor OpenTelemetry. Returns True if active."""
    global _configured, _tracer
    if _configured:
        return _tracer is not None

    _configured = True
    cs = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not cs:
        return False

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor  # type: ignore
        from opentelemetry import trace  # type: ignore
    except Exception as exc:
        logger.info("azure-monitor-opentelemetry not available: %r", exc)
        return False

    try:
        configure_azure_monitor(connection_string=cs, logger_name="app")
        _tracer = trace.get_tracer("macro-oil-terminal")
        logger.info("Application Insights connected.")
        return True
    except Exception as exc:
        logger.warning("App Insights configure failed: %r", exc)
        return False


def tracer():
    """Return the active tracer or a nullcontext-producing stand-in."""
    class _NullTracer:
        def start_as_current_span(self, *a, **kw):
            return nullcontext()

    return _tracer if _tracer is not None else _NullTracer()


def trace_event(name: str, /, **attrs: Any) -> None:
    """Record a span event with attributes. No-op if AI isn't configured."""
    if _tracer is None:
        return
    try:
        from opentelemetry import trace  # type: ignore
        span = trace.get_current_span()
        if span is None:
            return
        # attrs must be primitives (str/bool/int/float); coerce everything
        safe = {}
        for k, v in attrs.items():
            if isinstance(v, (str, bool, int, float)):
                safe[k] = v
            else:
                safe[k] = repr(v)
        span.add_event(name, attributes=safe)
    except Exception as exc:
        logger.debug("trace_event failed: %r", exc)


@contextmanager
def span(name: str, **attrs: Any):
    """Tiny convenience wrapper for one-shot spans."""
    t = tracer()
    with t.start_as_current_span(name) as s:
        if s is not None and attrs:
            for k, v in attrs.items():
                if isinstance(v, (str, bool, int, float)):
                    try:
                        s.set_attribute(k, v)
                    except Exception:
                        pass
        yield s


__all__ = ["configure", "tracer", "trace_event", "span"]
