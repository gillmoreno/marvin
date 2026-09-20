#!/usr/bin/env python3
"""Build Marvin logo files: square mark + horizontal lockup, as SVG / PNG / JPEG."""

from __future__ import annotations

from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTCollection
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Avenir Next.ttc"
DEMI = 2  # AvenirNext-DemiBold

# Room First palette (dark + teal)
RAIL = "#161920"
ACCENT = "#2dd4bf"  # teal/green
CREAM = "#f5f3ee"

# Backward-compat alias
GOLD = ACCENT

# Speech circle from the in-app mark (24×24 viewBox).
MARK_PATH = "M7.9 20A9 9 0 1 0 4 16.1L2 22Z"
MARK_PIP = (15.7, 9.6)

# Lockup matches the approved board: 96px mark, 72px word, 28px gap, 0.12em tracking.
MARK_PX = 96
FONT_PX = 72
GAP_PX = 28
TRACK_EM = 0.12


def glyph_d(glyph_set, name: str) -> str:
    pen = SVGPathPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.getCommands()


def lockup_svg(bg: str | None = None) -> str:
    font = TTCollection(FONT).fonts[DEMI]
    glyph_set = font.getGlyphSet()
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    upm = font["head"].unitsPerEm
    scale = FONT_PX / upm
    track = TRACK_EM * FONT_PX

    names = ["M", "a", "r", "v", "dotlessi", "n"]
    x = 0.0
    letters: list[tuple[str, float]] = []
    for name in names:
        letters.append((glyph_d(glyph_set, name), x))
        x += hmtx[name][0] * scale + track
    word_w = x - track

    i_origin = letters[4][1]
    tittle = glyf["i"].coordinates[4:]  # contour 1: the tittle
    tx = [p[0] for p in tittle]
    ty = [p[1] for p in tittle]
    pip_cx = i_origin + (min(tx) + max(tx)) / 2 * scale
    pip_cy = (min(ty) + max(ty)) / 2 * scale
    pip_r = (max(tx) - min(tx)) / 2 * scale * 1.08

    word_top = max(glyf[n].yMax for n in ["M", "a", "r", "v", "i", "n"]) * scale
    word_bot = min(glyf[n].yMin for n in ["M", "a", "r", "v", "i", "n"]) * scale
    word_cx = word_w / 2
    word_cy = (word_top + word_bot) / 2

    mark_scale = MARK_PX / 24
    # SVG y grows down; letters sit above the baseline (negative y).
    # Park the bubble's visual centre on the word's visual centre.
    mark_x = 0
    mark_y = -word_cy - 11 * mark_scale
    gap = GAP_PX
    text_x = MARK_PX + gap
    text_y = 0  # baseline; glyphs flip up from here

    content_w = MARK_PX + gap + word_w
    content_top = min(mark_y, -word_top)
    content_bot = max(mark_y + MARK_PX, -word_bot)
    pad_x = 8
    pad_y = 10
    vb_x = -pad_x
    vb_y = content_top - pad_y
    vb_w = content_w + pad_x * 2
    vb_h = (content_bot - content_top) + pad_y * 2

    bg_rect = (
        f'<rect x="{vb_x:.2f}" y="{vb_y:.2f}" width="{vb_w:.2f}" height="{vb_h:.2f}" fill="{bg}"/>'
        if bg
        else ""
    )
    letter_paths = "\n".join(
        f'    <path d="{d}" transform="translate({text_x + ox:.3f} {text_y:.3f}) scale({scale:.6f} {-scale:.6f})" fill="{CREAM}"/>'
        for d, ox in letters
    )
    pip_svg_y = text_y - pip_cy
    pip_svg_x = text_x + pip_cx

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb_x:.2f} {vb_y:.2f} {vb_w:.2f} {vb_h:.2f}" fill="none">
  {bg_rect}
  <g transform="translate({mark_x:.3f} {mark_y:.3f}) scale({mark_scale:.6f})">
    <path d="{MARK_PATH}" stroke="{ACCENT}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="{MARK_PIP[0]}" cy="{MARK_PIP[1]}" r="3.4" fill="{ACCENT}" fill-opacity="0.22"/>
    <circle cx="{MARK_PIP[0]}" cy="{MARK_PIP[1]}" r="2.05" fill="{ACCENT}"/>
  </g>
  <g>
{letter_paths}
    <circle cx="{pip_svg_x:.3f}" cy="{pip_svg_y:.3f}" r="{(pip_r * 1.55):.3f}" fill="{ACCENT}" fill-opacity="0.28"/>
    <circle cx="{pip_svg_x:.3f}" cy="{pip_svg_y:.3f}" r="{pip_r:.3f}" fill="{ACCENT}"/>
  </g>
</svg>
'''


def mark_svg(bg: str | None = None, canvas: float = 48) -> str:
    """Square mark. 24-unit icon inset in `canvas` so the bubble has room to breathe."""
    inset = (canvas - 24) / 2
    bg_rect = f'<rect width="{canvas}" height="{canvas}" fill="{bg}"/>' if bg else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}" fill="none">
  {bg_rect}
  <g transform="translate({inset} {inset})">
    <path d="{MARK_PATH}" stroke="{ACCENT}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="{MARK_PIP[0]}" cy="{MARK_PIP[1]}" r="3.4" fill="{ACCENT}" fill-opacity="0.22"/>
    <circle cx="{MARK_PIP[0]}" cy="{MARK_PIP[1]}" r="2.05" fill="{ACCENT}"/>
  </g>
</svg>
'''


def rasterize(svg: str, png_path: Path, width: int, height: int, bg: str, svg_width: int) -> None:
    html = f"""<!doctype html>
<style>
  html, body {{ margin: 0; background: {bg}; width: {width}px; height: {height}px; }}
  .stage {{ width: {width}px; height: {height}px; display: grid; place-items: center; background: {bg}; }}
  svg {{ display: block; width: {svg_width}px; height: auto; }}
</style>
<div class="stage">{svg}</div>
"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
        page.set_content(html)
        page.wait_for_selector("svg")
        page.locator(".stage").screenshot(path=str(png_path), type="png")
        browser.close()


def png_to_jpg(png_path: Path, jpg_path: Path, bg: str) -> None:
    src = Image.open(png_path).convert("RGBA")
    ground = Image.new("RGB", src.size, bg)
    ground.paste(src, mask=src.split()[-1])
    ground.save(jpg_path, "JPEG", quality=94, optimize=True, subsampling=0)


def write(path: Path, text: str) -> None:
    path.write_text(text)
    print("wrote", path.name)


def favicon_svg() -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="7" fill="{RAIL}"/>
  <g fill="none" transform="translate(4 4)">
    <path d="{MARK_PATH}" stroke="{ACCENT}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="{MARK_PIP[0]}" cy="{MARK_PIP[1]}" r="3.4" fill="{ACCENT}" fill-opacity="0.22"/>
    <circle cx="{MARK_PIP[0]}" cy="{MARK_PIP[1]}" r="2.05" fill="{ACCENT}"/>
  </g>
</svg>
'''


def main() -> None:
    lockup = lockup_svg()
    lockup_on_rail = lockup_svg(bg=RAIL)
    mark = mark_svg(canvas=48)
    mark_on_rail = mark_svg(bg=RAIL, canvas=48)
    mark_ui = mark_svg(canvas=24)

    write(ROOT / "marvin-lockup.svg", lockup)
    write(ROOT / "marvin-mark.svg", mark)

    public = ROOT.parent / "web" / "public"
    write(public / "marvin-lockup.svg", lockup)
    write(public / "marvin-mark.svg", mark_ui)
    write(public / "favicon.svg", favicon_svg())

    rasterize(lockup_on_rail, ROOT / "marvin-lockup.png", 2560, 1440, RAIL, svg_width=1480)
    rasterize(mark_on_rail, ROOT / "marvin-mark.png", 1024, 1024, RAIL, svg_width=560)
    print("wrote marvin-lockup.png")
    print("wrote marvin-mark.png")

    png_to_jpg(ROOT / "marvin-lockup.png", ROOT / "marvin-lockup.jpg", RAIL)
    png_to_jpg(ROOT / "marvin-mark.png", ROOT / "marvin-mark.jpg", RAIL)
    print("wrote marvin-lockup.jpg")
    print("wrote marvin-mark.jpg")


if __name__ == "__main__":
    main()
