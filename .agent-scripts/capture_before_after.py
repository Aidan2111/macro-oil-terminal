"""Capture the 5-screenshot before/after pack for UIP T10.

Screenshots produced (into OUT_DIR):
    hero_desktop.png    1440x1800 full-page
    macro_tab.png       Tab 1 visible (Spread Stretch)
    depletion_tab.png   Tab 2 visible (Inventory drawdown)
    fleet_tab.png       Tab 3 visible (Tanker fleet)
    hero_mobile.png     375x812

Usage:
    python .agent-scripts/capture_before_after.py <URL> <OUT_DIR>
"""

from __future__ import annotations

import pathlib
import sys
import time

from playwright.sync_api import sync_playwright


# Ordered list of tab labels to try. The pre-polish build uses "Spread
# dislocation"; the polished build uses "Spread Stretch".
TABS = [
    ("macro_tab", ["Spread Stretch", "Spread dislocation"]),
    ("depletion_tab", ["Inventory drawdown"]),
    ("fleet_tab", ["Tanker fleet"]),
]


def _wait_for_app(page, timeout_ms: int = 120_000) -> None:
    """Wait until the hero-band is visible (Streamlit over websocket)."""
    try:
        page.locator('[data-testid="hero-band"]').first.wait_for(
            state="visible", timeout=timeout_ms
        )
    except Exception:
        pass
    # Give Plotly / WebGPU a moment to paint
    time.sleep(4)


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: capture_before_after.py <URL> <OUT_DIR>", file=sys.stderr)
        return 2
    url = sys.argv[1]
    out_dir = pathlib.Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ---- Desktop 1440x1800 --------------------------------------------
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 1800},
            device_scale_factor=1,
        )
        page = ctx.new_page()
        print(f"[desktop] goto {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        _wait_for_app(page)

        hero = out_dir / "hero_desktop.png"
        page.screenshot(path=str(hero), full_page=True)
        print(f"wrote {hero}")

        for slug, labels in TABS:
            clicked = False
            last_exc: Exception | None = None
            for label in labels:
                try:
                    page.get_by_role("tab", name=label).click(timeout=5_000)
                    clicked = True
                    break
                except Exception as exc:
                    last_exc = exc
            if not clicked:
                print(f"!! tab {labels!r} failed: {last_exc!r}")
                continue
            time.sleep(3.0)
            shot = out_dir / f"{slug}.png"
            page.screenshot(path=str(shot), full_page=True)
            print(f"wrote {shot}")

        ctx.close()

        # ---- Mobile 375x812 -----------------------------------------------
        ctx_m = browser.new_context(
            viewport={"width": 375, "height": 812},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
        page_m = ctx_m.new_page()
        print(f"[mobile] goto {url}")
        page_m.goto(url, wait_until="domcontentloaded", timeout=90_000)
        _wait_for_app(page_m)
        hero_m = out_dir / "hero_mobile.png"
        page_m.screenshot(path=str(hero_m), full_page=False)
        print(f"wrote {hero_m}")
        ctx_m.close()

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
