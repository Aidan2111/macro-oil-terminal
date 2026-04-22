"""Sanity checks on the committed GitHub Actions workflows."""

from __future__ import annotations

import pathlib


WORKFLOWS = pathlib.Path(".github/workflows")


def test_workflow_files_present():
    for w in ("ci.yml", "cd.yml", "keep-warm.yml", "codeql.yml", "release.yml"):
        assert (WORKFLOWS / w).is_file(), f"missing {w}"


def test_cd_uses_oidc_and_test_gate():
    txt = (WORKFLOWS / "cd.yml").read_text()
    assert "id-token: write" in txt
    assert "azure/login@v2" in txt
    assert "test_runner.py" in txt or "pytest" in txt


def test_release_builds_notes():
    txt = (WORKFLOWS / "release.yml").read_text()
    assert "PROGRESS.md diff" in txt
    assert "gh release create" in txt


def test_dependabot_present():
    txt = pathlib.Path(".github/dependabot.yml").read_text()
    assert "pip" in txt and "github-actions" in txt
