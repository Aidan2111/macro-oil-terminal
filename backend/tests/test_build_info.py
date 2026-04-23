"""Build-info endpoint tests.

Override the filesystem path via `BACKEND_BUILD_INFO_PATH` so the test
doesn't depend on the deploy pipeline having stamped the file.
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


def test_build_info_returns_expected_keys(build_info_file: Path):
    """GET /api/build-info returns {sha, time, region} at minimum."""
    client = TestClient(create_app())
    response = client.get("/api/build-info")
    assert response.status_code == 200
    payload = response.json()
    assert set(["sha", "time", "region"]).issubset(payload.keys())
    assert payload["sha"] == "abcdef1234567890"
    assert payload["time"] == "2026-04-23T10:00:00Z"
    assert payload["region"] == "canadaeast"


def test_build_info_falls_back_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Missing file → synthesized 'unknown' payload, never 500."""
    missing = tmp_path / "does-not-exist.json"
    monkeypatch.setenv("BACKEND_BUILD_INFO_PATH", str(missing))
    client = TestClient(create_app())
    response = client.get("/api/build-info")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sha"] == "unknown"
    assert "time" in payload
    assert "region" in payload
