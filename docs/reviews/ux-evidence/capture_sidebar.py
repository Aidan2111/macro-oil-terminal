from pathlib import Path
from playwright.sync_api import sync_playwright
URL = "https://oil-tracker-app-canadaeast-4474.azurewebsites.net"
OUT = Path("/Users/aidanbothost/Documents/macro_oil_terminal/docs/reviews/ux-evidence")

def wait_ready(page):
    for _ in range(40):
        page.wait_for_timeout(1500)
        try:
            if page.locator('button[role="tab"]').count() >= 3:
                break
        except Exception:
            pass
    page.wait_for_timeout(3000)

def run(vp_name, w, h, mobile=False):
    with sync_playwright() as p:
        b = p.chromium.launch()
        kw = {"viewport":{"width":w,"height":h}}
        if mobile:
            kw.update(is_mobile=True, has_touch=True, device_scale_factor=2)
        ctx = b.new_context(**kw)
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=180000)
        wait_ready(page)
        # find any button that opens sidebar
        btn = page.locator('[data-testid="stExpandSidebarButton"]').first
        btn.click(force=True)
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / f"{vp_name}_sidebar_open_fixed.png"))
        b.close()

run("iphone13", 375, 812, mobile=True)
run("pixel7", 412, 915, mobile=True)
print("done")
