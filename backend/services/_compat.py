"""Sys.path compat shim for the service layer.

The root of the repo hosts legacy modules (``quantitative_models``,
``language``, ``providers/``, ``data_ingestion``) that were written for
the Streamlit app. The FastAPI backend lives under ``backend/`` and
imports from them directly rather than duplicating logic.

Importing this module adds the repo root to ``sys.path`` so those
top-level modules resolve cleanly from inside ``backend.services.*``.

Every service module does ``from . import _compat  # noqa: F401`` at the
top before touching any legacy module — and that's the only contract.
The shim is idempotent.
"""

from __future__ import annotations

import pathlib
import sys

# backend/services/_compat.py → parents[2] == repo root
_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
