"""Build-info endpoint tests.

Override the filesystem path via ``BACKEND_BUILD_INFO_PATH`` so the
tests don't depend on the deploy pipeline having stamped the file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def build_info_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "build-info.json"
    path.write_text(
        json.dumps(
            {
                "sha": "abcdef1234567890",
                "sha_short": "abcdef1",
                "time": "2026-04-23T10:00:00Z",
                "region": "canadaeast",
                "workflow_run": "12345",
            }
        )
    )
    monkeypatch.setenv("BACKEND_BUILD_INFO_PATH", str(path))
    return path


def test_build_info_happy_path(build_info_file: Path) -> None:
    """GET /api/build-info returns the full stamped payload."""
    client = TestClient(create_app())
    response = client.get("/api/build-info")
    assert response.status_code == 200
    payload = response.json()
    assert {"sha", "sha_short", "time", "region", "workflow_run"}.issubset(payload.keys())
    assert payload["sha"] == "abcdef1234567890"
    assert payload["sha_short"] == "abcdef1"
    assert payload["time"] == "2026-04-23T10:00:00Z"
    assert payload["region"] == "canadaeast"
    assert payload["workflow_run"] == "12345"


def test_build_info_falls_back_to_dev_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing file → {"sha": "dev", ...}, never 500."""
    missing = tmp_path / "does-not-exist.json"
    monkeypatch.setenv("BACKEND_BUILD_INFO_PATH", str(missing))
    client = TestClient(create_app())
    response = client.get("/api/build-info")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sha"] == "dev"
    assert "time" in payload
    assert "region" in payload


def test_build_info_raises_on_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unreadable JSON → 500 via the router's HTTPException branch."""
    bad = tmp_path / "build-info.json"
    bad.write_text("{not valid json")
    monkeypatch.setenv("BACKEND_BUILD_INFO_PATH", str(bad))
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get("/api/build-info")
    assert response.status_code == 500
