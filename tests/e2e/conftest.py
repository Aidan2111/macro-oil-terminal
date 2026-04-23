"""End-to-end fixtures: boot a headless Streamlit, share a Playwright browser."""

from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import time

import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_healthy(proc: subprocess.Popen, port: int, deadline_s: int = 60) -> None:
    """Block until the Streamlit health endpoint returns 200 or raise."""
    import urllib.request

    url_health = f"http://127.0.0.1:{port}/_stcore/health"
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url_health, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(1)
    proc.terminate()
    raise RuntimeError(
        f"Streamlit never became healthy on :{port} within {deadline_s}s."
    )


def _spawn_streamlit(port: int, extra_env: dict | None = None) -> subprocess.Popen:
    """Spawn a headless Streamlit subprocess rooted at the repo top."""
    root = pathlib.Path(__file__).resolve().parents[2]

    env = os.environ.copy()
    # Keep it deterministic + offline: no live LLM, no live yfinance
    # hits from the e2e runner — the app handles those failures cleanly.
    env.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    env.setdefault("STREAMLIT_BROWSER_GATHERUSAGESTATS", "false")
    if extra_env:
        env.update(extra_env)

    return subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.headless=true",
            f"--server.port={port}",
            "--server.address=127.0.0.1",
            "--browser.gatherUsageStats=false",
        ],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


@pytest.fixture(scope="session")
def streamlit_server():
    """Start `streamlit run app.py` once per session; stop at teardown."""
    port = int(os.environ.get("E2E_STREAMLIT_PORT") or _free_port())
    proc = _spawn_streamlit(port)
    _wait_for_healthy(proc, port, deadline_s=60)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


@pytest.fixture(scope="session")
def streamlit_server_mock_auth():
    """Streamlit booted with MOCK_AUTH_USER=e2e@example.com, STREAMLIT_ENV=dev.

    Used by Task-5 e2e tests that exercise the signed-in header caption
    without needing a real Google OIDC round-trip.
    """
    port = int(os.environ.get("E2E_STREAMLIT_PORT_MOCK") or _free_port())
    proc = _spawn_streamlit(
        port,
        extra_env={
            "MOCK_AUTH_USER": "e2e@example.com",
            "STREAMLIT_ENV": "dev",
        },
    )
    _wait_for_healthy(proc, port, deadline_s=60)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


@pytest.fixture(scope="session")
def browser():
    """Reuse a single Chromium browser across the e2e session."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright Chromium unavailable: {exc!r}")
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1800})
    p = ctx.new_page()
    yield p
    ctx.close()
