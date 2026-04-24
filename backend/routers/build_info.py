"""Build-info endpoint.

Reads a JSON file stamped at deploy time by the CD workflow. The path
is configurable via `BACKEND_BUILD_INFO_PATH` so tests can inject a
fixture. Returns a `BuildInfo` pydantic model.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..models.build_info import BuildInfo

router = APIRouter(tags=["build-info"])


_DEFAULT_PATH = "static/build-info.json"


def _build_info_path() -> Path:
    return Path(os.environ.get("BACKEND_BUILD_INFO_PATH", _DEFAULT_PATH))


@router.get("/build-info", response_model=BuildInfo)
def build_info() -> BuildInfo:
    """Return the stamped build info, or a sensible fallback."""
    path = _build_info_path()
    if not path.exists():
        # Local dev convenience — no file yet, synthesise a payload.
        # Spec: fallback is {"sha": "dev", ...} so the frontend can show
        # a clear "local/unstamped" indicator.
        return BuildInfo(
            sha="dev",
            sha_short="dev",
            time="1970-01-01T00:00:00Z",
            region=os.environ.get("BACKEND_REGION", "local"),
        )

    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"build-info unreadable: {exc}",
        ) from exc

    return BuildInfo(
        sha=str(raw.get("sha", "unknown")),
        time=str(raw.get("time", "1970-01-01T00:00:00Z")),
        region=str(raw.get("region", "unknown")),
        sha_short=raw.get("sha_short"),
        workflow_run=raw.get("workflow_run"),
    )
