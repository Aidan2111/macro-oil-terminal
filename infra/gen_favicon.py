"""Regenerate ``static/favicon.ico`` from ``static/logo.svg``.

Primary path uses cairosvg + Pillow — cairosvg rasterises the checked-in
SVG at 128 px, then Pillow packs a multi-resolution ICO with the four
standard sizes.

If cairosvg isn't importable (libcairo system deps are finicky on
macOS), we fall back to a pure-Pillow drawing that approximates the
barrel + dislocation arrow composition. Either path produces a valid
multi-size ICO that ships in the repo.

Usage::

    python infra/gen_favicon.py

Dependencies::

    pip install cairosvg pillow   # preferred
    pip install pillow            # fallback still works
"""

from __future__ import annotations

import io
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SVG_PATH = REPO_ROOT / "static" / "logo.svg"
ICO_PATH = REPO_ROOT / "static" / "favicon.ico"
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64)]


def _generate_with_cairosvg():
    """Preferred path — rasterise the checked-in SVG via cairosvg."""
    import cairosvg
    from PIL import Image

    png_bytes = cairosvg.svg2png(
        url=str(SVG_PATH),
        output_width=128,
        output_height=128,
    )
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    img.save(ICO_PATH, format="ICO", sizes=ICO_SIZES)


def _generate_with_pillow_only():
    """Fallback — draw the barrel + split arrow in Pillow primitives.

    Produces a visually similar mark: dark tile, cyan barrel outline
    with three rib stripes, cyan arrow shaft splitting into two heads.
    Works without libcairo so the build is portable on fresh macOS.
    """
    from PIL import Image, ImageDraw

    # Draw at 256 px for crisp downsampling, then let Pillow resample.
    size = 256
    bg = (10, 14, 26, 255)       # #0A0E1A
    fg = (34, 211, 238, 255)     # #22D3EE

    img = Image.new("RGBA", (size, size), bg)
    draw = ImageDraw.Draw(img)

    # Rounded tile — leave a 1-px inset so the corner isn't hard-cropped.
    # (Pillow >= 8.2 has rounded_rectangle; the base tile is already the
    # full bg, so we only need the barrel + arrow on top.)

    # --- Barrel ------------------------------------------------------
    # Coordinates are scaled from the 64 px SVG viewBox (x4).
    stroke = 8  # scales ~2 px stroke from the 64 px viewBox.

    # Body — rounded rectangle.
    bx0, by0, bx1, by1 = 48, 56, 136, 200
    try:
        draw.rounded_rectangle(
            (bx0, by0, bx1, by1), radius=14, outline=fg, width=stroke,
        )
    except AttributeError:
        draw.rectangle((bx0, by0, bx1, by1), outline=fg, width=stroke)

    # Top + bottom ellipses (cylinder caps).
    draw.ellipse((bx0 - 4, by0 - 10, bx1 + 4, by0 + 10), outline=fg, width=stroke)
    draw.ellipse((bx0 - 4, by1 - 10, bx1 + 4, by1 + 10), outline=fg, width=stroke)

    # Rib stripes.
    for y in (92, 128, 164):
        draw.line((bx0, y, bx1, y), fill=fg, width=stroke)

    # --- Dislocation arrow -------------------------------------------
    # Shaft out of the right edge.
    draw.line((144, 128, 184, 128), fill=fg, width=stroke)

    # Upper branch: up-right head.
    draw.line((184, 128, 216, 88), fill=fg, width=stroke)
    draw.line((196, 88, 216, 88), fill=fg, width=stroke)
    draw.line((216, 88, 216, 108), fill=fg, width=stroke)

    # Lower branch: down-right head.
    draw.line((184, 128, 216, 168), fill=fg, width=stroke)
    draw.line((196, 168, 216, 168), fill=fg, width=stroke)
    draw.line((216, 168, 216, 148), fill=fg, width=stroke)

    img.save(ICO_PATH, format="ICO", sizes=ICO_SIZES)


def main() -> int:
    if not SVG_PATH.exists():
        print(f"error: {SVG_PATH} not found", file=sys.stderr)
        return 1
    ICO_PATH.parent.mkdir(exist_ok=True)

    try:
        _generate_with_cairosvg()
        print(f"wrote {ICO_PATH} via cairosvg")
        return 0
    except Exception as exc:
        print(f"cairosvg path failed ({exc}); falling back to Pillow-only")

    try:
        _generate_with_pillow_only()
        print(f"wrote {ICO_PATH} via Pillow-only fallback")
        return 0
    except Exception as exc:
        print(f"error: Pillow fallback also failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
