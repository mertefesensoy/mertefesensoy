#!/usr/bin/env python3
"""Render the prepared portrait as a tiered, edge-aware, self-printing SVG.

Version 2 of the portrait renderer.  Each cell of a 150 by 80 grid carries a
glyph, one of six luminance tiers (each tier has its own ink and glyph ramp),
and an edge flag.  The portrait prints in three passes, shadows first, mids,
then lights, so it develops like a photographic print rather than wiping in
row by row.  Motion plays once and is disabled under reduced-motion.

    python scripts/make_ascii_svg.py            # animated
    python scripts/make_ascii_svg.py --static   # no entrance motion

Contracts
---------
``portrait_to_cells(path) -> list[list[Cell]]``
    Reads the prepped grayscale, returns ROWS lists of COLS cells.  Pure.
``render_svg(cells, *, static=False) -> str``
    Serialises the cells to SVG text.  Pure.  Raises ValueError on a grid of
    the wrong shape.

Invariants the tests rely on: exactly ROWS text rows, one cursor per row per
pass, six tier classes, no ``infinite`` animation, a reduced-motion rule, and
a subject glyph density between 0.30 and 0.60 of the grid.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "assets" / "profile-prepped.png"
DEFAULT_OUTPUT = ROOT / "assets" / "mert-ascii.svg"

WIDTH = 840
HEIGHT = 875
COLS = 150
ROWS = 80
ART_WIDTH = 800
ART_HEIGHT = 795
CELL_WIDTH = ART_WIDTH / COLS
CELL_HEIGHT = ART_HEIGHT / ROWS
PADDING = 20
TITLEBAR_HEIGHT = 30

ROW_STEP = 0.025  # seconds between rows inside one pass
PASS_GAP = 2.2  # seconds between the start of consecutive passes
PASSES = ("pa", "pb", "pc")  # shadows, mids, lights
TOTAL_RUN = PASS_GAP * 2 + ROW_STEP * ROWS + 0.4

TONE_GAMMA = 0.92
BACKGROUND_LUMINANCE = 0.97  # at or above this a cell is empty
TIER_COUNT = 6
EDGE_PERCENTILE = 85.0

# Tier 0 is the brightest lit tone, tier 5 the deepest shadow.
# Ink: blue shadows rising to ivory light (owner's choice, 2026-10-25).
TIER_INK = ("#f8f1e0", "#e6dcc6", "#bcbdcf", "#6a93e6", "#3a68c9", "#2b4f9c")
# Glyph ramps run darker to brighter inside the tier, so coverage keeps
# rising with luminance across the whole range.
TIER_GLYPHS = (
    ("%", "@", "@"),
    ("#", "%", "@"),
    ("X", "#", "%"),
    ("*", "x", "X"),
    ("=", "+", "*"),
    ("-", "~", "="),
)
TIER_PASS = ("pc", "pc", "pb", "pb", "pa", "pa")


@dataclass(frozen=True)
class Cell:
    glyph: str
    tier: int  # -1 for background
    edge: bool


def _subject_window(image: Image.Image) -> Image.Image:
    """Crop the prepped square to the subject, square, anchored to the bottom.

    The source has a lot of paper above the head.  Framing the subject makes
    the face about twice as large on the grid.
    """

    pixels = np.asarray(image)
    subject = np.argwhere(pixels < 250)
    if subject.size == 0:
        return image
    top, left = subject.min(axis=0)
    bottom, right = subject.max(axis=0)
    height, width = pixels.shape
    side = int(max(right - left, bottom - top) * 1.06)
    side = min(side, width, height)
    centre_x = (left + right) // 2
    x0 = int(min(max(0, centre_x - side // 2), width - side))
    y0 = int(max(0, top - side * 0.03))
    if y0 + side > height:
        y0 = height - side
    return image.crop((x0, y0, x0 + side, y0 + side))


def _edge_glyph(gx: float, gy: float) -> str:
    """Pick a structural glyph from the gradient direction (edge is normal to it)."""

    angle = math.degrees(math.atan2(gy, gx)) % 180.0
    if angle < 22.5 or angle >= 157.5:
        return "|"  # gradient horizontal, edge vertical
    if 67.5 <= angle < 112.5:
        return "-"  # gradient vertical, edge horizontal
    # Diagonal: gradient pointing down-right means the edge runs up-right.
    return "/" if gx * gy > 0 else "\\"


def portrait_to_cells(path: Path) -> list[list[Cell]]:
    with Image.open(path) as source:
        image = source.convert("L")
    image = _subject_window(image)

    # Luminance grid at cell resolution.
    grid = image.resize((COLS, ROWS), Image.Resampling.LANCZOS)
    grid = grid.filter(ImageFilter.UnsharpMask(radius=0.7, percent=120, threshold=2))
    lum = (np.asarray(grid, dtype=np.float32) / 255.0) ** TONE_GAMMA
    background = lum >= BACKGROUND_LUMINANCE
    darkness = 1.0 - lum

    # Stretch the subject's darkness range so all six tiers are populated.
    subject_values = darkness[~background]
    if subject_values.size:
        lo, hi = np.percentile(subject_values, (2.0, 98.0))
    else:
        lo, hi = 0.0, 1.0
    stretched = np.clip((darkness - lo) / max(1e-6, hi - lo), 0.0, 0.999999)
    scaled = stretched * TIER_COUNT
    tier = np.floor(scaled).astype(int)  # 0 bright .. 5 dark
    sub = np.floor((scaled - tier) * 3).astype(int)

    # Gradients on an isotropic copy so the cell aspect does not bias them.
    iso = image.resize((COLS, round(COLS * ART_HEIGHT / ART_WIDTH)), Image.Resampling.LANCZOS)
    iso_lum = np.asarray(iso, dtype=np.float32) / 255.0
    gy_iso, gx_iso = np.gradient(iso_lum)
    # Pool the isotropic gradient rows down to the cell rows.
    rows_per_cell = iso_lum.shape[0] / ROWS
    gx = np.zeros((ROWS, COLS), dtype=np.float32)
    gy = np.zeros((ROWS, COLS), dtype=np.float32)
    for r in range(ROWS):
        a = int(r * rows_per_cell)
        b = max(a + 1, int((r + 1) * rows_per_cell))
        gx[r] = gx_iso[a:b].mean(axis=0)
        gy[r] = gy_iso[a:b].mean(axis=0)
    magnitude = np.hypot(gx, gy)
    subject_magnitude = magnitude[~background]
    threshold = float(np.percentile(subject_magnitude, EDGE_PERCENTILE)) if subject_magnitude.size else 1.0

    cells: list[list[Cell]] = []
    for y in range(ROWS):
        row: list[Cell] = []
        for x in range(COLS):
            if background[y, x]:
                row.append(Cell(" ", -1, False))
                continue
            t = int(tier[y, x])
            is_edge = magnitude[y, x] >= threshold
            if is_edge:
                glyph = _edge_glyph(float(gx[y, x]), float(gy[y, x]))
            else:
                glyph = TIER_GLYPHS[t][int(sub[y, x])]
            row.append(Cell(glyph, t, is_edge))
        cells.append(row)
    return cells


def _row_tspans(row: list[Cell]) -> str:
    """Merge consecutive same-tier cells into tspans; background stays plain."""

    parts: list[str] = []
    buffer: list[str] = []
    current = -2
    for cell in row:
        if cell.tier != current:
            if buffer:
                parts.append(_flush(buffer, current))
                buffer = []
            current = cell.tier
        buffer.append(cell.glyph)
    if buffer:
        parts.append(_flush(buffer, current))
    return "".join(parts)


def _flush(buffer: list[str], tier: int) -> str:
    text = escape("".join(buffer))
    if tier < 0:
        return text
    return f'<tspan class="t{tier} {TIER_PASS[tier]}">{text}</tspan>'


def _style() -> str:
    tiers = "\n".join(
        f"          .t{index} {{ fill:{ink}; }}" for index, ink in enumerate(TIER_INK)
    )
    return f"""
          text {{ font-family:'IBM Plex Mono','Cascadia Mono','SFMono-Regular',Consolas,monospace; }}
          .micro {{ fill:#7185a8; font-size:11px; font-weight:600; letter-spacing:1.15px; }}
          .label {{ fill:#78a9ff; font-size:11px; font-weight:700; letter-spacing:1.05px; }}
          .status {{ fill:#42be65; font-size:11px; font-weight:700; letter-spacing:.9px; }}
          .ascii-row {{ font-size:{CELL_HEIGHT * 0.94:.2f}px; font-weight:600; fill:#d0e2ff; }}
{tiers}
          .pa {{ --pass:0s; }}
          .pb {{ --pass:{PASS_GAP:.2f}s; }}
          .pc {{ --pass:{PASS_GAP * 2:.2f}s; }}
          .row-cursor {{ opacity:0; }}
          .cursor-a {{ fill:#3a68c9; --pass:0s; }}
          .cursor-b {{ fill:#78a9ff; --pass:{PASS_GAP:.2f}s; }}
          .cursor-c {{ fill:#f8f1e0; --pass:{PASS_GAP * 2:.2f}s; }}
          .prompt {{ fill:#9fb2d1; font-size:13px; }}
          .prompt-value {{ fill:#f2f6fc; font-weight:700; }}
          .pass-tag {{ fill:#7185a8; font-size:10px; font-weight:600; letter-spacing:1px; opacity:0; }}
          @keyframes ink-in {{ from {{ fill-opacity:0; }} to {{ fill-opacity:1; }} }}
          @keyframes sweep-cursor {{
            0% {{ opacity:.9; transform:translateX(0); }}
            85% {{ opacity:.9; transform:translateX({ART_WIDTH}px); }}
            100% {{ opacity:0; transform:translateX({ART_WIDTH}px); }}
          }}
          @keyframes tag-in {{ to {{ opacity:1; }} }}
          @keyframes prompt-cursor {{ 0%,49% {{ opacity:1; }} 50%,100% {{ opacity:.16; }} }}
          @media (prefers-reduced-motion:no-preference) {{
            .portrait:not(.static) .ascii-row tspan {{
              fill-opacity:0;
              animation:ink-in .12s linear forwards;
              animation-delay:calc(var(--pass) + var(--row));
            }}
            .portrait:not(.static) .row-cursor {{
              animation:sweep-cursor .06s linear forwards;
              animation-delay:calc(var(--pass) + var(--row));
            }}
            .portrait:not(.static) .pass-tag {{ animation:tag-in .01s linear forwards; animation-delay:var(--pass); }}
            .portrait:not(.static) .prompt-cursor {{ animation:prompt-cursor 1.1s step-end 3; animation-delay:{TOTAL_RUN:.2f}s; }}
          }}
          @media (prefers-reduced-motion:reduce) {{
            .ascii-row tspan {{ animation:none !important; fill-opacity:1 !important; }}
            .row-cursor {{ animation:none !important; opacity:0 !important; }}
            .pass-tag {{ animation:none !important; opacity:1 !important; }}
            .prompt-cursor {{ animation:none !important; }}
          }}
          .portrait.static .pass-tag {{ opacity:1; }}
"""


def render_svg(cells: list[list[Cell]], *, static: bool = False) -> str:
    if len(cells) != ROWS or any(len(row) != COLS for row in cells):
        raise ValueError(f"Expected a {COLS}x{ROWS} cell grid")

    root_class = "portrait static" if static else "portrait"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
            f'aria-labelledby="portrait-title portrait-desc" class="{root_class}" focusable="false">'
        ),
        '<title id="portrait-title">Mert Efe Şensoy, tiered ASCII portrait</title>',
        (
            '<desc id="portrait-desc">A monochrome ASCII portrait of Mert Efe Şensoy develops in three '
            'passes inside an IBM-inspired SYSPLEX terminal: blue shadows print first, then the mid '
            'tones, then ivory highlights, with structural glyphs tracing the jaw, collar and lapel.</desc>'
        ),
        "<defs>",
        '<pattern id="portrait-grid" width="58" height="58" patternUnits="userSpaceOnUse"><path d="M58 0H0V58" fill="none" stroke="#4589ff" stroke-opacity=".04"/></pattern>',
        '<pattern id="portrait-scan" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M0 3.5H840" stroke="#f2f6fc" stroke-opacity=".025"/></pattern>',
        "<style>",
        _style(),
        "</style>",
        "</defs>",
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#07090e"/>',
        f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{HEIGHT - 1}" fill="#080e18" stroke="#27466f"/>',
        f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" fill="url(#portrait-grid)"/>',
        f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" fill="url(#portrait-scan)"/>',
        f'<rect x="1" y="1" width="4" height="{HEIGHT - 2}" fill="#4589ff"/>',
        f'<rect x="5" y="1" width="{WIDTH - 6}" height="29" fill="#050a11"/>',
        f'<path d="M5 30H{WIDTH - 1}" stroke="#27466f"/>',
        '<text x="22" y="20" class="label">MERTEFE.SYSPLEX // PORTRAIT.PRINT</text>',
        '<text x="300" y="20" class="micro">150x80 · 6 TIERS · 3 PASSES</text>',
        '<circle cx="665" cy="15" r="3" fill="#42be65"/>',
        '<text x="676" y="20" class="status">JOB ACTIVE</text>',
        f'<text x="{WIDTH - 22}" y="20" class="micro" text-anchor="end">F1=HELP</text>',
    ]

    art_top = TITLEBAR_HEIGHT + 7
    font_y_offset = CELL_HEIGHT * 0.78
    for index, row in enumerate(cells):
        row_y = art_top + index * CELL_HEIGHT
        baseline = row_y + font_y_offset
        delay = index * ROW_STEP
        parts.append(
            f'<text xml:space="preserve" x="{PADDING}" y="{baseline:.1f}" class="ascii-row" '
            f'style="--row:{delay:.3f}s" textLength="{ART_WIDTH}" lengthAdjust="spacing">'
            f"{_row_tspans(row)}</text>"
        )
        for suffix in ("a", "b", "c"):
            parts.append(
                f'<rect class="row-cursor cursor-{suffix}" style="--row:{delay:.3f}s" x="{PADDING}" '
                f'y="{row_y + 1:.1f}" width="{CELL_WIDTH:.2f}" height="{CELL_HEIGHT - 2:.2f}"/>'
            )

    status_line_y = TITLEBAR_HEIGHT + ART_HEIGHT + 7
    parts.extend(
        [
            f'<path d="M5 {status_line_y}H{WIDTH - 1}" stroke="#27466f"/>',
            f'<text x="22" y="{status_line_y + 21}" class="prompt">mertefe@sysplex:~$ whoami '
            '<tspan class="prompt-value">Mert Efe Şensoy</tspan></text>',
            f'<rect class="prompt-cursor" x="350" y="{status_line_y + 8}" width="8" height="15" fill="#78a9ff"/>',
            f'<text x="520" y="{status_line_y + 21}" class="pass-tag pa">PASS 1 SHADOWS</text>',
            f'<text x="625" y="{status_line_y + 21}" class="pass-tag pb">· 2 MIDS</text>',
            f'<text x="690" y="{status_line_y + 21}" class="pass-tag pc">· 3 LIGHTS</text>',
            f'<text x="{WIDTH - 22}" y="{status_line_y + 21}" class="micro" text-anchor="end">RC=0000</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--static", action="store_true", help="Disable entrance animations")
    args = parser.parse_args()

    cells = portrait_to_cells(args.input)
    svg = render_svg(cells, static=args.static)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8", newline="\n")
    filled = sum(1 for row in cells for cell in row if cell.tier >= 0)
    edges = sum(1 for row in cells for cell in row if cell.edge)
    print(
        f"Wrote {args.output} ({COLS}x{ROWS}, {filled} subject cells, {edges} edge cells, "
        f"{len(svg.encode('utf-8')) / 1024:.0f} KB)"
    )


if __name__ == "__main__":
    main()
