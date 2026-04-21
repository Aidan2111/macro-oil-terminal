"""Capture per-tab screenshots of the running Streamlit app using Playwright.

Run after `streamlit run app.py` is live on 127.0.0.1:8611.
"""

from __future__ import annotations

import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

OUT_DIR = pathlib.Path("docs/screenshots")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8611"
    tabs = [
        ("01_macro_arbitrage", "Macro Arbitrage"),
        ("02_depletion_forecast", "Depletion Forecast"),
        ("03_fleet_analytics", "Fleet Analytics"),
        ("04_ai_insights", "AI Insights"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 2000},
            device_scale_factor=1,
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=45_000)
        # Let Streamlit + Plotly finish rendering
        time.sleep(4)

        # Overview shot
        overview = OUT_DIR / "00_overview.png"
        page.screenshot(path=str(overview), full_page=True)
        print(f"wrote {overview}")

        for slug, label in tabs:
            try:
                page.get_by_role("tab", name=label).click(timeout=5_000)
                time.sleep(2.5)  # allow chart rerender
                shot = OUT_DIR / f"{slug}.png"
                page.screenshot(path=str(shot), full_page=True)
                print(f"wrote {shot}")
            except Exception as exc:
                print(f"!! tab {label} failed: {exc!r}")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
