#!/usr/bin/env python3
"""Render the prepared portrait as a self-printing IBM terminal SVG.

The composition follows the useful architecture demonstrated by
AVIVASHISHTA29's public profile—one text node and one wipe per ASCII row—but
the implementation, styling, accessibility, and static fallback are original.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "assets" / "profile-prepped.png"
DEFAULT_OUTPUT = ROOT / "assets" / "mert-ascii.svg"

WIDTH = 840
HEIGHT = 875
COLS = 120
ROWS = 64
ART_WIDTH = 800
ART_HEIGHT = 795
CELL_WIDTH = ART_WIDTH / COLS
CELL_HEIGHT = ART_HEIGHT / ROWS
ROW_DURATION = 0.09
PADDING = 20
TITLEBAR_HEIGHT = 30
ASCII_RAMP = " .,:;-=+*xX#%@"
TONE_GAMMA = 0.90


def portrait_to_ascii(path: Path) -> list[str]:
    with Image.open(path) as source:
        image = source.convert("L")
    image = image.resize((COLS, ROWS), Image.Resampling.LANCZOS)
    image = image.filter(ImageFilter.UnsharpMask(radius=0.8, percent=170, threshold=2))
    image = ImageEnhance.Contrast(image).enhance(1.08)
    pixels = image.load()

    rows: list[str] = []
    for y in range(ROWS):
        characters: list[str] = []
        for x in range(COLS):
            luminance = (pixels[x, y] / 255.0) ** TONE_GAMMA
            if luminance >= 0.97:
                characters.append(" ")
                continue
            index = round((1.0 - luminance) * (len(ASCII_RAMP) - 1))
            characters.append(ASCII_RAMP[max(0, min(index, len(ASCII_RAMP) - 1))])
        rows.append("".join(characters))
    return rows


def render_svg(rows: list[str], *, static: bool = False) -> str:
    if len(rows) != ROWS:
        raise ValueError(f"Expected {ROWS} ASCII rows, received {len(rows)}")

    root_class = "portrait static" if static else "portrait"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
            f'aria-labelledby="portrait-title portrait-desc" class="{root_class}" focusable="false">'
        ),
        '<title id="portrait-title">Mert Efe Şensoy — animated ASCII portrait</title>',
        (
            '<desc id="portrait-desc">A high-detail monochrome portrait prints from top to bottom inside an '
            'IBM-inspired SYSPLEX terminal and resolves to Mert Efe Şensoy.</desc>'
        ),
        '<defs>',
        '<pattern id="portrait-grid" width="58" height="58" patternUnits="userSpaceOnUse"><path d="M58 0H0V58" fill="none" stroke="#4589ff" stroke-opacity=".04"/></pattern>',
        '<pattern id="portrait-scan" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M0 3.5H840" stroke="#f2f6fc" stroke-opacity=".025"/></pattern>',
        '<style>',
        """
          text { font-family:'IBM Plex Mono','Cascadia Mono','SFMono-Regular',Consolas,monospace; }
          .micro { fill:#7185a8; font-size:11px; font-weight:600; letter-spacing:1.15px; }
          .label { fill:#78a9ff; font-size:11px; font-weight:700; letter-spacing:1.05px; }
          .status { fill:#42be65; font-size:11px; font-weight:700; letter-spacing:.9px; }
          .ascii-row { fill:#d0e2ff; font-size:10.8px; font-weight:600; }
          .row-clip { transform:scaleX(1); transform-box:fill-box; transform-origin:left center; }
          .row-cursor { opacity:0; transform:translateX(800px); }
          .prompt { fill:#9fb2d1; font-size:13px; }
          .prompt-value { fill:#f2f6fc; font-weight:700; }
          @keyframes reveal-row { from { transform:scaleX(0); } to { transform:scaleX(1); } }
          @keyframes sweep-cursor {
            0% { opacity:.88; transform:translateX(0); }
            88% { opacity:.88; transform:translateX(800px); }
            100% { opacity:0; transform:translateX(800px); }
          }
          @keyframes prompt-cursor { 0%,49% { opacity:1; } 50%,100% { opacity:.16; } }
          @media (prefers-reduced-motion:no-preference) {
            .portrait:not(.static) .row-clip {
              animation:reveal-row .09s linear both;
              animation-delay:var(--delay);
            }
            .portrait:not(.static) .row-cursor {
              animation:sweep-cursor .09s linear forwards;
              animation-delay:var(--delay);
            }
            .portrait:not(.static) .prompt-cursor { animation:prompt-cursor 1.1s step-end 3; animation-delay:5.86s; }
          }
          @media (prefers-reduced-motion:reduce) {
            .row-clip { animation:none !important; transform:scaleX(1) !important; }
            .row-cursor { animation:none !important; opacity:0 !important; }
            .prompt-cursor { animation:none !important; }
          }
        """,
        '</style>',
    ]

    art_top = TITLEBAR_HEIGHT + 7
    for index in range(ROWS):
        row_y = art_top + index * CELL_HEIGHT
        delay = index * ROW_DURATION
        parts.append(
            f'<clipPath id="portrait-row-{index}"><rect class="row-clip" '
            f'style="--delay:{delay:.3f}s" x="{PADDING}" y="{row_y:.1f}" '
            f'width="{ART_WIDTH}" height="{CELL_HEIGHT}"/></clipPath>'
        )
    parts.extend(
        [
            '</defs>',
            '<rect width="840" height="875" fill="#07090e"/>',
            '<rect x=".5" y=".5" width="839" height="874" fill="#080e18" stroke="#27466f"/>',
            '<rect x="1" y="1" width="838" height="873" fill="url(#portrait-grid)"/>',
            '<rect x="1" y="1" width="838" height="873" fill="url(#portrait-scan)"/>',
            '<rect x="1" y="1" width="4" height="873" fill="#4589ff"/>',
            '<rect x="5" y="1" width="834" height="29" fill="#050a11"/>',
            '<path d="M5 30H839" stroke="#27466f"/>',
            '<text x="22" y="20" class="label">MERTEFE.SYSPLEX // PORTRAIT.PRINT</text>',
            '<circle cx="665" cy="15" r="3" fill="#42be65"/>',
            '<text x="676" y="20" class="status">JOB ACTIVE</text>',
            '<text x="818" y="20" class="micro" text-anchor="end">F1=HELP</text>',
        ]
    )

    font_y_offset = CELL_HEIGHT * 0.77
    for index, row in enumerate(rows):
        row_y = art_top + index * CELL_HEIGHT
        baseline = row_y + font_y_offset
        delay = index * ROW_DURATION
        parts.append(
            f'<text xml:space="preserve" x="{PADDING}" y="{baseline:.1f}" '
            f'class="ascii-row" textLength="{ART_WIDTH}" lengthAdjust="spacing" '
            f'clip-path="url(#portrait-row-{index})">{escape(row)}</text>'
        )
        parts.append(
            f'<rect class="row-cursor" style="--delay:{delay:.3f}s" x="{PADDING}" '
            f'y="{row_y + 1:.1f}" width="{CELL_WIDTH:.2f}" height="{CELL_HEIGHT - 2:.2f}" fill="#78a9ff"/>'
        )

    status_line_y = TITLEBAR_HEIGHT + ART_HEIGHT + 7
    parts.extend(
        [
            f'<path d="M5 {status_line_y}H839" stroke="#27466f"/>',
            f'<text x="22" y="{status_line_y + 21}" class="prompt">mertefe@sysplex:~$ whoami '
            '<tspan class="prompt-value">Mert Efe Şensoy</tspan></text>',
            f'<rect class="prompt-cursor" x="350" y="{status_line_y + 8}" width="8" height="15" fill="#78a9ff"/>',
            f'<text x="818" y="{status_line_y + 21}" class="micro" text-anchor="end">RC=0000 // COMPLETE</text>',
            '</svg>',
        ]
    )
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--static", action="store_true", help="Disable entrance animations")
    args = parser.parse_args()

    rows = portrait_to_ascii(args.input)
    svg = render_svg(rows, static=args.static)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} ({len(rows)} ASCII rows, {WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
