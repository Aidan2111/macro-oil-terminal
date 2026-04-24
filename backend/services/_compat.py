"""Compatibility shim — reaches the root-level Python modules.

The root-level ``trade_thesis`` / ``quantitative_models`` / ``thesis_context``
modules live in the legacy Streamlit tree (one level above ``backend/``).
Importing them from inside ``backend.*`` on every test run is fragile when
pytest's ``rootdir`` differs; this shim fixes ``sys.path`` once and re-exports
the handful of symbols the FastAPI services need.

Sub-A is growing this into a richer adapter layer (context builder, alert
plumbing, etc.). Until that lands, the minimum surface required by Sub-B is
implemented here — the merge-up will replace this file with Sub-A's version.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any, Callable, Optional

# Add the repo root (one level above backend/) to sys.path so we can import
# trade_thesis.py / quantitative_models.py that still live there.
_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_trade_thesis() -> Any:
    """Import the legacy ``trade_thesis`` module lazily so unit tests can
    monkey-patch the shim without pulling in ``openai`` et al at import time.
    """
    import trade_thesis  # type: ignore  # noqa: E402

    return trade_thesis


def _load_quant() -> Any:
    import quantitative_models  # type: ignore  # noqa: E402

    return quantitative_models


def generate_thesis(
    ctx: Any,
    *,
    mode: str = "fast",
    stream_handler: Optional[Callable[[str], None]] = None,
    log: bool = True,
) -> Any:
    """Thin wrapper around ``trade_thesis.generate_thesis``."""
    tt = _load_trade_thesis()
    return tt.generate_thesis(
        ctx, mode=mode, stream_handler=stream_handler, log=log
    )


def read_recent_theses(n: int = 10) -> list[dict]:
    """Re-export of ``trade_thesis.read_recent_theses``."""
    tt = _load_trade_thesis()
    return tt.read_recent_theses(n)


def audit_log_path() -> pathlib.Path:
    """Return the JSONL audit path used by ``trade_thesis._append_audit``."""
    tt = _load_trade_thesis()
    return pathlib.Path(tt._AUDIT_PATH)


def build_thesis_context() -> Any:
    """Return a :class:`ThesisContext` built from live data.

    Sub-A's richer shim wires this to ``thesis_context.build_context``; the
    minimal version here defers to whatever that module exposes and raises a
    clear error if it is not available. The SSE route only calls this when a
    client actually posts to /api/thesis/generate, so pure unit tests of the
    routers never touch it.
    """
    try:
        import thesis_context  # type: ignore  # noqa: E402
    except Exception as exc:  # pragma: no cover — legacy module present in repo
        raise RuntimeError(
            "thesis_context module unavailable — wire Sub-A's context builder"
        ) from exc

    # The legacy module exposes either ``build_context`` or a helper named
    # after a specific flow; try the common names in order so either works.
    for attr in ("build_thesis_context", "build_context", "get_thesis_context"):
        fn = getattr(thesis_context, attr, None)
        if callable(fn):
            return fn()

    raise RuntimeError(
        "thesis_context has no build_context()/build_thesis_context() entry"
    )


def backtest_zscore_meanreversion(
    spread_df: Any,
    *,
    entry_z: float = 2.0,
    exit_z: float = 0.2,
    notional_bbls: float = 10_000.0,
    slippage_per_bbl: float = 0.0,
    commission_per_trade: float = 0.0,
) -> dict:
    """Wrapper over ``quantitative_models.backtest_zscore_meanreversion``."""
    qm = _load_quant()
    return qm.backtest_zscore_meanreversion(
        spread_df,
        entry_z=entry_z,
        exit_z=exit_z,
        notional_bbls=notional_bbls,
        slippage_per_bbl=slippage_per_bbl,
        commission_per_trade=commission_per_trade,
    )


__all__ = [
    "audit_log_path",
    "backtest_zscore_meanreversion",
    "build_thesis_context",
    "generate_thesis",
    "read_recent_theses",
]
