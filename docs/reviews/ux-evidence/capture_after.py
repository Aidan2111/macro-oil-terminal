"""Capture after-state screenshots for UX revision v2.

Boots the local Streamlit app on an ephemeral port, navigates via
Playwright, captures desktop (1440x900) + mobile (375x812) shots, and
writes them to ``docs/reviews/ux-evidence/after/``. Run from the repo
root with the venv activated:

    python docs/reviews/ux-evidence/capture_after.py

Screenshots captured (mirrors a subset of the "before" set):
    after/desktop_landing.png
    after/desktop_landing_full.png
    after/iphone13_landing.png
    after/iphone13_landing_full.png
    after/iphone13_sidebar_open.png
    after/desktop_tab_spread_stretch.png
    after/desktop_tab_inventory_drawdown.png
    after/desktop_tab_tanker_fleet.png

Enough to compare hero / sticky-tabs / sign-in CTA / sidebar chevron
against the persona-11 before-state captures in the same directory.
"""

from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright


ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent / "after"
OUT.mkdir(parents=True, exist_ok=True)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(port, deadline_s=90):
    import urllib.request
    url = f"http://127.0.0.1:{port}/_stcore/health"
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def _spawn_streamlit(port):
    env = os.environ.copy()
    env.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    env.setdefault("STREAMLIT_BROWSER_GATHERUSAGESTATS", "false")
    return subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.headless=true",
            f"--server.port={port}",
            "--server.address=127.0.0.1",
            "--browser.gatherUsageStats=false",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_app(page):
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
        state="visible", timeout=90_000
    )
    page.wait_for_timeout(2500)


def _capture_desktop(url):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        _wait_app(page)
        page.screenshot(path=str(OUT / "desktop_landing.png"))
        page.screenshot(
            path=str(OUT / "desktop_landing_full.png"), full_page=True
        )
        # Tab shots — click each tab, capture viewport.
        for tab_label, slug in (
            ("Spread Stretch", "spread_stretch"),
            ("Inventory drawdown", "inventory_drawdown"),
            ("Tanker fleet", "tanker_fleet"),
        ):
            try:
                page.evaluate("window.scrollTo(0, 0)")
                page.locator(
                    f'button[role="tab"]:has-text("{tab_label}")'
                ).first.click()
                page.wait_for_timeout(2500)
                page.screenshot(path=str(OUT / f"desktop_tab_{slug}.png"))
            except Exception as exc:
                print(f"desktop tab {slug} failed: {exc!r}")
        ctx.close()
        b.close()


def _capture_iphone13(url):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(
            viewport={"width": 375, "height": 812},
            is_mobile=True,
            has_touch=True,
            device_scale_factor=2,
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        _wait_app(page)
        page.screenshot(path=str(OUT / "iphone13_landing.png"))
        page.screenshot(
            path=str(OUT / "iphone13_landing_full.png"), full_page=True
        )
        # Open sidebar to capture the 44x44 chevron in its expanded state.
        try:
            btn = page.locator(
                '[data-testid="stExpandSidebarButton"], '
                '[data-testid="stSidebarCollapsedControl"]'
            ).first
            if btn.count() > 0:
                btn.click()
                page.wait_for_timeout(1500)
                page.screenshot(path=str(OUT / "iphone13_sidebar_open.png"))
        except Exception as exc:
            print(f"sidebar capture failed: {exc!r}")
        ctx.close()
        b.close()


def main():
    port = _free_port()
    proc = _spawn_streamlit(port)
    try:
        if not _wait_healthy(port):
            print("Streamlit never became healthy", file=sys.stderr)
            sys.exit(1)
        url = f"http://127.0.0.1:{port}"
        print("capturing desktop…")
        _capture_desktop(url)
        print("capturing iphone13…")
        _capture_iphone13(url)
        print(f"screenshots written to {OUT}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
