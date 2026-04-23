"""
Capture screenshots + DOM evidence against the live deployed Macro Oil Terminal.
Writes PNGs and a JSON dossier to docs/reviews/ux-evidence/.
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://oil-tracker-app-canadaeast-4474.azurewebsites.net"
OUT = Path("/Users/aidanbothost/Documents/macro_oil_terminal/docs/reviews/ux-evidence")
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORTS = {
    "iphone13":  {"width": 375,  "height": 812, "mobile": True,  "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"},
    "pixel7":    {"width": 412,  "height": 915, "mobile": True,  "ua": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Mobile Safari/537.36"},
    "desktop":   {"width": 1440, "height": 900, "mobile": False, "ua": None},
}

TABS = ["Spread Stretch", "Inventory drawdown", "Tanker fleet"]

DOM_SCAN_JS = r"""
() => {
  const out = {};
  const all = Array.from(document.querySelectorAll('*'));
  const text_elems = all.filter(el => el.childNodes && Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim().length > 0));
  const fs = new Map();
  const lh = new Map();
  text_elems.forEach(el => {
    const cs = getComputedStyle(el);
    fs.set(cs.fontSize, (fs.get(cs.fontSize)||0)+1);
    lh.set(cs.lineHeight, (lh.get(cs.lineHeight)||0)+1);
  });
  out.font_sizes = Object.fromEntries([...fs.entries()].sort((a,b)=>b[1]-a[1]));
  out.line_heights = Object.fromEntries([...lh.entries()].sort((a,b)=>b[1]-a[1]));

  // tap targets
  const taps = Array.from(document.querySelectorAll('button, a, [role=tab], [role=button], input[type=checkbox], input[type=range], summary'));
  out.taps = taps.filter(e=>{
    const r = e.getBoundingClientRect();
    return r.width>0 && r.height>0;
  }).map(e => {
    const r = e.getBoundingClientRect();
    return {
      tag: e.tagName,
      role: e.getAttribute('role') || '',
      txt: (e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,60),
      w: Math.round(r.width),
      h: Math.round(r.height),
      x: Math.round(r.x),
      y: Math.round(r.y),
    };
  });

  // horizontal scroll
  out.scrollW = document.documentElement.scrollWidth;
  out.clientW = document.documentElement.clientWidth;
  out.innerW  = window.innerWidth;
  out.h_overflow = document.documentElement.scrollWidth > window.innerWidth;

  // color contrast helper
  function parseRgb(s){
    const m = s.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    if(!m) return null;
    return {r:+m[1], g:+m[2], b:+m[3], a: m[4]===undefined?1:+m[4]};
  }
  function relLum({r,g,b}){
    const s = [r,g,b].map(v=>{v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4);});
    return 0.2126*s[0]+0.7152*s[1]+0.0722*s[2];
  }
  function effectiveBg(el){
    let e = el;
    while(e){
      const cs = getComputedStyle(e);
      const bg = parseRgb(cs.backgroundColor);
      if(bg && bg.a > 0.001) return bg;
      e = e.parentElement;
    }
    return {r:255,g:255,b:255,a:1};
  }
  function contrast(fg, bg){
    const l1 = relLum(fg), l2 = relLum(bg);
    const [a,b] = l1>l2?[l1,l2]:[l2,l1];
    return (a+0.05)/(b+0.05);
  }
  // sample text nodes — pick elements with direct text > 1 char
  const samples = [];
  text_elems.slice(0, 800).forEach(el => {
    const cs = getComputedStyle(el);
    const fg = parseRgb(cs.color);
    if(!fg) return;
    const bg = effectiveBg(el);
    const cr = contrast(fg, bg);
    const txt = (Array.from(el.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ')||'').trim();
    if(!txt) return;
    samples.push({
      txt: txt.slice(0,80),
      fs: cs.fontSize,
      fw: cs.fontWeight,
      color: cs.color,
      bg: `rgb(${bg.r},${bg.g},${bg.b})`,
      contrast: +cr.toFixed(2),
    });
  });
  out.contrast_samples = samples;
  out.low_contrast = samples.filter(s => s.contrast < 4.5).slice(0,40);
  return out;
}
"""

def wait_ready(page):
    for _ in range(40):
        page.wait_for_timeout(1500)
        try:
            tabs = page.locator('button[role="tab"]').count()
            running = page.locator('text="Running"').count()
            if tabs >= 3 and running == 0:
                break
        except Exception:
            pass
    page.wait_for_timeout(2500)

def click_tab(page, label):
    page.locator(f'button[role="tab"]:has-text("{label}")').first.click()
    page.wait_for_timeout(4000)
    # wait for plotly chart to render on the tab
    page.wait_for_timeout(1500)

def scroll_top(page):
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(500)

def full_scroll_capture(page, path):
    # Streamlit renders everything; use full_page screenshot
    page.screenshot(path=str(path), full_page=True)

def capture(vp_name, vp):
    print(f"\n== {vp_name} {vp['width']}x{vp['height']} ==")
    dossier = {"viewport": vp_name, "dims": [vp["width"], vp["height"]], "tabs": {}}
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx_kwargs = {"viewport": {"width": vp["width"], "height": vp["height"]}}
        if vp["ua"]:
            ctx_kwargs["user_agent"] = vp["ua"]
        if vp["mobile"]:
            ctx_kwargs["is_mobile"] = True
            ctx_kwargs["has_touch"] = True
            ctx_kwargs["device_scale_factor"] = 2
        ctx = b.new_context(**ctx_kwargs)
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=180000)
        wait_ready(page)
        scroll_top(page)

        # landing (hero) — viewport only
        page.screenshot(path=str(OUT / f"{vp_name}_landing.png"))
        # full page landing
        full_scroll_capture(page, OUT / f"{vp_name}_landing_full.png")
        dossier["tabs"]["landing"] = page.evaluate(DOM_SCAN_JS)

        # each tab
        for tab in TABS:
            slug = tab.lower().replace(" ", "_")
            scroll_top(page)
            try:
                click_tab(page, tab)
            except Exception as e:
                print("tab click failed", tab, e)
            page.wait_for_timeout(3500)
            # viewport screenshot
            page.screenshot(path=str(OUT / f"{vp_name}_tab_{slug}.png"))
            # full page
            full_scroll_capture(page, OUT / f"{vp_name}_tab_{slug}_full.png")
            dossier["tabs"][slug] = page.evaluate(DOM_SCAN_JS)

        # interactive states on desktop only
        if vp_name == "desktop":
            # go back to landing
            scroll_top(page)
            try:
                click_tab(page, "Spread Stretch")
            except Exception:
                pass
            # Move the "Alert when stretched" slider — first range input
            try:
                sliders = page.locator('input[type="range"], [role="slider"]').all()
                print("sliders found:", len(sliders))
                if sliders:
                    sliders[0].focus()
                    for _ in range(8):
                        page.keyboard.press("ArrowRight")
                        page.wait_for_timeout(150)
                    page.wait_for_timeout(1500)
                    page.screenshot(path=str(OUT / f"{vp_name}_slider_moved.png"), full_page=False)
            except Exception as e:
                print("slider interaction failed", e)
            # Toggle Show advanced metrics
            try:
                toggle = page.locator('text="Show advanced metrics"').first
                toggle.click()
                page.wait_for_timeout(1500)
                page.screenshot(path=str(OUT / f"{vp_name}_advanced_toggled.png"), full_page=True)
            except Exception as e:
                print("toggle failed", e)

        # mobile: capture sidebar (if collapsed)
        if vp["mobile"]:
            scroll_top(page)
            try:
                # Streamlit sidebar toggle
                btn = page.locator('[data-testid="stSidebarCollapsedControl"], button[kind="header"]').first
                if btn.count():
                    btn.click()
                    page.wait_for_timeout(1200)
                    page.screenshot(path=str(OUT / f"{vp_name}_sidebar_open.png"))
            except Exception as e:
                print("sidebar open failed", e)

        ctx.close(); b.close()
    with open(OUT / f"_dom_{vp_name}.json","w") as f:
        json.dump(dossier, f, indent=2, default=str)
    print(f"dossier written: _dom_{vp_name}.json")

if __name__ == "__main__":
    for name, vp in VIEWPORTS.items():
        try:
            capture(name, vp)
        except Exception as e:
            print("CAPTURE FAIL", name, e)
