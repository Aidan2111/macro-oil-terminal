"""Shared shim for services that cross the backend/root boundary.

Lets the backend/services/* modules import from the repo root
(`providers.*`, `data_ingestion`, etc.) without each one repeating the
sys.path juggling. Sub-A and Sub-B use the same file on their branches.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root lives two levels up from this file.
_ROOT = Path(__file__).resolve().parents[2]
_ROOT_STR = str(_ROOT)
if _ROOT_STR not in sys.path:
    sys.path.insert(0, _ROOT_STR)


def repo_root() -> Path:
    """Absolute path of the repository root (for read-only access)."""
    return _ROOT


def env(name: str, default: str | None = None) -> str | None:
    """Thin wrapper around os.environ.get; here so tests can stub it."""
    return os.environ.get(name, default)
