"""
Annotate key screenshots with red boxes + labels documenting UX issues.
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path("/Users/aidanbothost/Documents/macro_oil_terminal/docs/reviews/ux-evidence")

def font(sz):
    for f in ["/System/Library/Fonts/Helvetica.ttc","/Library/Fonts/Arial.ttf","/System/Library/Fonts/SFNS.ttf"]:
        try: return ImageFont.truetype(f, sz)
        except Exception: pass
    return ImageFont.load_default()

RED = (232, 58, 58, 255)
AMBER = (255, 176, 0, 255)

def annotate(src, dest, boxes, scale=1.0):
    """boxes = [(x,y,w,h, label, color?)] using image coordinates."""
    img = Image.open(src).convert("RGBA")
    W,H = img.size
    overlay = Image.new("RGBA", img.size, (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    fsize = max(14, int(W*0.012))
    f = font(fsize)
    for box in boxes:
        x,y,w,h, label = box[:5]
        color = box[5] if len(box) > 5 else RED
        draw.rectangle([x,y,x+w,y+h], outline=color, width=4)
        # label bg
        bbox = draw.textbbox((0,0), label, font=f)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        lx, ly = x, max(0, y - th - 10)
        draw.rectangle([lx, ly, lx+tw+10, ly+th+8], fill=(0,0,0,220), outline=color, width=2)
        draw.text((lx+5, ly+3), label, fill=color, font=f)
    out = Image.alpha_composite(img, overlay)
    out.convert("RGB").save(dest, "PNG")
    print("wrote", dest)

# 1. iPhone landing: hero takes whole viewport, no above-the-fold data
annotate(
    OUT/"iphone13_landing.png",
    OUT/"iphone13_landing_annotated.png",
    [
        (16, 220, 340, 220, "A1. 36px headline eats entire above-the-fold. Zero price data visible on first paint."),
        (16, 470, 130, 95, "A2. 'trade idea not yet generated' chip — dark text on mid-gray pill, contrast 2.15:1 (AA fail)."),
    ]
)

# 2. iPhone invD_1 — Sign in with Google dominates Hero, CTA hierarchy inversion
annotate(
    OUT/"iphone13_invD_1.png",
    OUT/"iphone13_signin_annotated.png",
    [
        (30, 880, 300, 110, "B1. 'Sign in with Google' cyan CTA is the most visually prominent element on screen — user's eye jumps to auth, not verdict."),
        (30, 990, 700, 80, "B2. The actual verdict ('no clear trade opportunity') is plain body text under a blue button that isn't the primary action."),
        (16, 670, 720, 160, "B3. Mini 'HERO · STAND ASIDE' pill — chip text contrast 2.15:1 (WCAG fail); label is meta-copy that shipped to production ('HERO ·' is a layout tag)."),
    ]
)

# 3. Desktop landing — sidebar at 280/1440 = 19%, hero title wastes 400px vertical
annotate(
    OUT/"desktop_landing.png",
    OUT/"desktop_landing_annotated.png",
    [
        (16, 20, 300, 860, "C1. Sidebar is 280px wide (19% of viewport) yet contains 8 controls with 16px help-icon tap targets."),
        (316, 130, 1100, 110, "C2. H1 headline is 36px, 2 lines, repeats tagline. No price data, gauge, or trade idea above the fold at the top of the hero."),
        (316, 340, 1100, 160, "C3. 4 ticker cards share row width with a giant ASCII-style 'signal flow' WebGL banner — attention split."),
        (316, 690, 800, 100, "C4. 'HERO · STAND ASIDE' chip with 'Today's trade idea, sizing…' copy — the actual verdict sits BELOW in a second card. Two competing verdict surfaces."),
    ]
)

# 4. Desktop spread_stretch tab — ETF cards appear BEFORE chart + too many metric tiles
annotate(
    OUT/"desktop_tab_spread_stretch.png",
    OUT/"desktop_spread_annotated.png",
    [
        (316, 30, 1100, 90, "D1. 'No actionable catalyst' banner + 3 ETF 'execute — wiring' cards rendered above the chart on tab 1. Disclosure sequence: verdict → wiring-placeholder → finally chart."),
        (316, 360, 1100, 80, "D2. 5 KPI tiles: Latest, Spread, Cointegration, Half-life, Dynamic hedge. No thermometer/anchor to distinguish hero metric."),
        (316, 180, 1100, 120, "D3. Tab bar tucked UNDER the hero block — user must scroll past hero on every tab switch (3002px tall landing)."),
    ]
)

# 5. Pixel7 landing — cards overflow horizontally
annotate(
    OUT/"pixel7_landing.png",
    OUT/"pixel7_overflow_annotated.png",
    [
        (0, 520, 412, 90, "E1. Metric row clips off the right edge — 'WTI 92.96 sp...' cut without wrap or horizontal scroll hint."),
        (16, 280, 380, 140, "E2. Title still 36px on 412px viewport: three lines of headline before any datum is visible."),
        (15, 450, 110, 85, "E3. 'trade idea not yet generated' — same 2.15:1 low-contrast chip on mid-gray pill."),
    ]
)

print("annotations done")
