"""Unit tests for auth config boot checks (P1.1.6)."""
from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest


# --- helpers ---------------------------------------------------------------

_REQUIRED = (
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "STREAMLIT_COOKIE_SECRET",
)
_EITHER = ("STORAGE_ACCOUNT_CONNECTION_STRING", "STORAGE_ACCOUNT_NAME")


def _clear_auth_env(monkeypatch):
    for v in _REQUIRED + _EITHER + ("STREAMLIT_ENV",):
        monkeypatch.delenv(v, raising=False)


def _reset_warned(monkeypatch):
    # Reset the module-level _WARNED flag so dev-warn tests don't depend
    # on prior test ordering within the same process.
    monkeypatch.setattr("auth.config._WARNED", False)


# --- tests -----------------------------------------------------------------


def test_is_configured_false_when_nothing_set(monkeypatch):
    from auth.config import is_configured

    _clear_auth_env(monkeypatch)
    _reset_warned(monkeypatch)

    assert is_configured() is False


def test_is_configured_true_when_all_set(monkeypatch):
    from auth.config import is_configured

    _clear_auth_env(monkeypatch)
    _reset_warned(monkeypatch)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "csec")
    monkeypatch.setenv("STREAMLIT_COOKIE_SECRET", "cookie")
    monkeypatch.setenv("STORAGE_ACCOUNT_CONNECTION_STRING", "DefaultEndpointsProtocol=…")

    assert is_configured() is True


def test_boot_check_raises_in_prod_when_missing(monkeypatch):
    from auth.config import AuthNotConfigured, boot_check

    _clear_auth_env(monkeypatch)
    _reset_warned(monkeypatch)
    monkeypatch.setenv("STREAMLIT_ENV", "prod")

    with pytest.raises(AuthNotConfigured) as exc_info:
        boot_check()

    msg = str(exc_info.value)
    # The message must list each missing var by name so operators see
    # exactly what to set.
    for var in _REQUIRED:
        assert var in msg
    # And mention the either-of storage slot.
    assert "STORAGE_ACCOUNT_CONNECTION_STRING" in msg
    assert "STORAGE_ACCOUNT_NAME" in msg


def test_boot_check_warns_but_returns_in_dev_when_missing(monkeypatch, caplog):
    from auth.config import boot_check

    _clear_auth_env(monkeypatch)
    _reset_warned(monkeypatch)
    # Explicitly leave STREAMLIT_ENV unset — the dev path.

    with caplog.at_level(logging.WARNING, logger="auth.config"):
        boot_check()  # first call — should log
        first_count = sum(
            1 for r in caplog.records if "auth_not_configured" in r.getMessage()
        )
        boot_check()  # second call — should NOT log again
        second_count = sum(
            1 for r in caplog.records if "auth_not_configured" in r.getMessage()
        )

    assert first_count == 1, "boot_check should log once in dev"
    assert second_count == 1, "boot_check should NOT duplicate the warning"


def test_provision_auth_script_exists_and_is_executable():
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "infra" / "provision_auth.sh"

    assert script.is_file(), f"{script} must exist"
    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR, f"{script} must be executable by owner"

    first_line = script.read_text(encoding="utf-8").splitlines()[0]
    assert first_line in (
        "#!/usr/bin/env bash",
        "#!/bin/bash",
    ), f"unexpected shebang: {first_line!r}"
