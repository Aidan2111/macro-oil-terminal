"""Sanity checks on the committed GitHub Actions workflows."""

from __future__ import annotations

import pathlib
import re


WORKFLOWS = pathlib.Path(".github/workflows")


def test_workflow_files_present():
    # Streamlit-era cd.yml retired on 2026-04-26 alongside the wider
    # Streamlit teardown. The Next.js + FastAPI stack ships through
    # cd-nextjs.yml; the legacy Streamlit deploy no longer runs.
    for w in (
        "ci.yml",
        "cd-nextjs.yml",
        "ci-nextjs.yml",
        "keep-warm.yml",
        "codeql.yml",
        "release.yml",
    ):
        assert (WORKFLOWS / w).is_file(), f"missing {w}"


def test_cd_nextjs_uses_oidc_and_test_gate():
    txt = (WORKFLOWS / "cd-nextjs.yml").read_text()
    assert "id-token: write" in txt
    # Major version is allowed to drift (Dependabot promotes us through
    # azure/login@v2 -> @v3 -> ...). The OIDC contract is the same; only
    # the action's input/output shape may change. Match any major.
    assert re.search(r"azure/login@v\d+", txt), "cd-nextjs.yml must use azure/login OIDC"
    # Backend pipeline still has a smoke-import gate before deploy.
    assert "pytest" in txt or "smoke-import" in txt or "import ok" in txt


def test_release_builds_notes():
    txt = (WORKFLOWS / "release.yml").read_text()
    assert "PROGRESS.md diff" in txt
    assert "gh release create" in txt


def test_dependabot_present():
    txt = pathlib.Path(".github/dependabot.yml").read_text()
    assert "pip" in txt and "github-actions" in txt
