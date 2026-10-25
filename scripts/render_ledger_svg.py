#!/usr/bin/env python3
"""Render ``data/upstream_prs.json`` as the upstream-ledger console SVG.

Three count tiles, the latest merged pull requests, and one bar per
repository (merged solid, open hollow).  Motion plays once: tiles and rows
fade in, bars grow from the left.  Reduced motion shows the final state.
Standard library only; runs in the daily workflow.
"""

from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path
from typing import Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "upstream_prs.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "assets" / "pr-ledger.svg"

WIDTH = 860
HEIGHT = 340
TITLEBAR_HEIGHT = 30
LEFT = 22
TILE_W = 86
TILE_H = 64
TILE_GAP = 10
LIST_X = 322
LIST_ROWS = 6
BAR_ROWS = 6
BAR_Y = 196
BAR_PITCH = 20
BAR_LABEL_W = 230
BAR_MAX_W = WIDTH - LEFT - BAR_LABEL_W - 140


class RenderError(RuntimeError):
    """Raised when the ledger JSON is invalid."""


def load_ledger(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(f"unable to read {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RenderError("unsupported or missing ledger schema_version")
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        raise RenderError("stats must be an object")
    for field in ("merged", "open", "closed", "repositories"):
        value = stats.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RenderError(f"stats.{field} must be a non-negative integer")
    for field in ("repositories", "merged", "open"):
        if not isinstance(payload.get(field), list):
            raise RenderError(f"{field} must be an array")
    if not isinstance(payload.get("generated_at"), str):
        raise RenderError("generated_at must be a string")
    return payload


def _fit(text: str, width_px: float, char_px: float) -> str:
    limit = max(1, int(width_px // char_px))
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _style() -> str:
    return """
          text { font-family:'IBM Plex Mono','Cascadia Mono','SFMono-Regular',Consolas,monospace; }
          .micro { fill:#7185a8; font-size:11px; font-weight:600; letter-spacing:1.15px; }
          .label { fill:#78a9ff; font-size:11px; font-weight:700; letter-spacing:1.05px; }
          .status { fill:#42be65; font-size:11px; font-weight:700; letter-spacing:.9px; }
          .tile-key { fill:#7185a8; font-size:9.5px; font-weight:600; letter-spacing:1px; }
          .tile-value { fill:#f2f6fc; font-size:26px; font-weight:700; }
          .section { fill:#a6c8ff; font-size:10px; font-weight:700; letter-spacing:.9px; }
          .row-date { fill:#7185a8; font-size:10px; }
          .row-repo { fill:#78a9ff; font-size:10px; font-weight:600; }
          .row-title { fill:#d0e2ff; font-size:10px; }
          .bar-label { fill:#9fb2d1; font-size:10.5px; }
          .bar-count { fill:#f2f6fc; font-size:10.5px; font-weight:700; }
          .bar { transform:scaleX(1); transform-box:fill-box; transform-origin:left center; }
          .fade { opacity:1; }
          @keyframes grow { from { transform:scaleX(0); } to { transform:scaleX(1); } }
          @keyframes fade-in { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }
          @media (prefers-reduced-motion:no-preference) {
            .ledger:not(.static) .bar { animation:grow .6s cubic-bezier(.2,.8,.2,1) both; animation-delay:var(--d); }
            .ledger:not(.static) .fade { animation:fade-in .4s cubic-bezier(.2,.8,.2,1) both; animation-delay:var(--d); }
          }
          @media (prefers-reduced-motion:reduce) {
            .bar { animation:none !important; transform:scaleX(1) !important; }
            .fade { animation:none !important; opacity:1 !important; transform:none !important; }
          }
"""


def render_svg(ledger: Mapping[str, object], *, static: bool = False) -> str:
    stats = ledger["stats"]
    assert isinstance(stats, dict)
    repositories = ledger["repositories"]
    merged = ledger["merged"]
    assert isinstance(repositories, list) and isinstance(merged, list)
    generated = str(ledger["generated_at"])[:10]
    root_class = "ledger static" if static else "ledger"

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="ledger-title ledger-desc" '
            f'class="{root_class}" focusable="false">'
        ),
        '<title id="ledger-title">Upstream pull-request ledger</title>',
        (
            f'<desc id="ledger-desc">Public pull requests by Mert Efe Şensoy in repositories outside their own '
            f"organisations: {stats['merged']} merged, {stats['open']} open, across {stats['repositories']} "
            f"repositories, generated {escape(generated)} from GitHub search.</desc>"
        ),
        "<defs>",
        '<pattern id="lg-grid" width="58" height="58" patternUnits="userSpaceOnUse"><path d="M58 0H0V58" fill="none" stroke="#4589ff" stroke-opacity=".04"/></pattern>',
        '<pattern id="lg-scan" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M0 3.5H860" stroke="#f2f6fc" stroke-opacity=".025"/></pattern>',
        "<style>",
        _style(),
        "</style>",
        "</defs>",
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#07090e"/>',
        f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{HEIGHT - 1}" fill="#080e18" stroke="#27466f"/>',
        f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" fill="url(#lg-grid)"/>',
        f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" fill="url(#lg-scan)"/>',
        f'<rect x="1" y="1" width="4" height="{HEIGHT - 2}" fill="#4589ff"/>',
        f'<rect x="5" y="1" width="{WIDTH - 6}" height="29" fill="#050a11"/>',
        f'<path d="M5 30H{WIDTH - 1}" stroke="#27466f"/>',
        '<text x="22" y="20" class="label">MERTEFE.SYSPLEX // UPSTREAM.LEDGER</text>',
        '<text x="330" y="20" class="micro">PUBLIC PRs · OUTSIDE OWN ORGS</text>',
        '<circle cx="640" cy="15" r="3" fill="#42be65"/>',
        f'<text x="651" y="20" class="status">SYNCED {escape(generated)}</text>',
        f'<text x="{WIDTH - 22}" y="20" class="micro" text-anchor="end">F1=HELP</text>',
    ]

    # Tiles.
    tiles = (
        ("MERGED", stats["merged"], "#42be65"),
        ("OPEN", stats["open"], "#78a9ff"),
        ("REPOS", stats["repositories"], "#f2f6fc"),
    )
    y = TITLEBAR_HEIGHT + 20
    for index, (key, value, colour) in enumerate(tiles):
        x = LEFT + index * (TILE_W + TILE_GAP)
        parts.append(
            f'<g class="fade" style="--d:{0.1 + index * 0.08:.2f}s">'
            f'<rect x="{x}" y="{y}" width="{TILE_W}" height="{TILE_H}" rx="2" fill="#0b1422" stroke="#27466f"/>'
            f'<text x="{x + 10}" y="{y + 16}" class="tile-key">{key}</text>'
            f'<text x="{x + 10}" y="{y + 48}" class="tile-value" fill="{colour}">{value:,}</text>'
            "</g>"
        )
    last_merged = stats.get("last_merged")
    parts.append(
        f'<text x="{LEFT}" y="{y + TILE_H + 22}" class="micro">LAST MERGE '
        f"{escape(str(last_merged)) if last_merged else 'NONE YET'}</text>"
    )
    parts.append(
        f'<text x="{LEFT}" y="{y + TILE_H + 40}" class="micro">{stats["closed"]} CLOSED UNMERGED</text>'
    )

    # Latest merged list.
    parts.append(f'<text x="{LIST_X}" y="{y + 6}" class="section">LATEST MERGED</text>')
    list_w = WIDTH - LIST_X - LEFT
    for index, record in enumerate(merged[:LIST_ROWS]):
        if not isinstance(record, dict):
            continue
        row_y = y + 24 + index * 19
        repo = str(record.get("repo", ""))
        number = record.get("number", "")
        date = str(record.get("merged") or "")
        title = _fit(str(record.get("title", "")), list_w - 320, 6.0)
        parts.append(
            f'<g class="fade" style="--d:{0.35 + index * 0.07:.2f}s">'
            f'<text x="{LIST_X}" y="{row_y}" class="row-date">{escape(date)}</text>'
            f'<text x="{LIST_X + 78}" y="{row_y}" class="row-repo">{escape(_fit(f"{repo}#{number}", 230, 6.0))}</text>'
            f'<text x="{LIST_X + 318}" y="{row_y}" class="row-title">{escape(title)}</text>'
            "</g>"
        )
    if not merged:
        parts.append(f'<text x="{LIST_X}" y="{y + 24}" class="row-title">No merged upstream pull requests yet.</text>')

    # Repository bars.
    parts.append(f'<path d="M{LEFT} {BAR_Y - 22}H{WIDTH - LEFT}" stroke="#27466f"/>')
    parts.append(f'<text x="{LEFT}" y="{BAR_Y - 6}" class="section">BY REPOSITORY · MERGED SOLID · OPEN HOLLOW</text>')
    top = [entry for entry in repositories[:BAR_ROWS] if isinstance(entry, dict)]
    scale_max = max([int(e.get("merged", 0)) + int(e.get("open", 0)) for e in top] or [1])
    for index, entry in enumerate(top):
        row_y = BAR_Y + 12 + index * BAR_PITCH
        merged_n = int(entry.get("merged", 0))
        open_n = int(entry.get("open", 0))
        merged_w = max(1.0, BAR_MAX_W * merged_n / scale_max) if merged_n else 0.0
        open_w = max(1.0, BAR_MAX_W * open_n / scale_max) if open_n else 0.0
        bar_x = LEFT + BAR_LABEL_W
        delay = 0.5 + index * 0.08
        parts.append(
            f'<text x="{LEFT}" y="{row_y + 4}" class="bar-label">{escape(_fit(str(entry.get("repo", "")), BAR_LABEL_W - 10, 6.3))}</text>'
        )
        if merged_w:
            parts.append(
                f'<rect class="bar" style="--d:{delay:.2f}s" x="{bar_x}" y="{row_y - 5}" width="{merged_w:.1f}" height="10" fill="#4589ff"/>'
            )
        if open_w:
            parts.append(
                f'<rect class="bar" style="--d:{delay + 0.1:.2f}s" x="{bar_x + merged_w + (2 if merged_w else 0):.1f}" y="{row_y - 4.5}" '
                f'width="{open_w:.1f}" height="9" fill="none" stroke="#78a9ff"/>'
            )
        label = f"{merged_n} merged" + (f" · {open_n} open" if open_n else "")
        parts.append(
            f'<text class="fade bar-count" style="--d:{delay + 0.3:.2f}s" x="{bar_x + merged_w + open_w + 10:.1f}" y="{row_y + 4}">{label}</text>'
        )
    if not top:
        parts.append(f'<text x="{LEFT}" y="{BAR_Y + 16}" class="row-title">No upstream repositories yet.</text>')

    parts.append(
        f'<text x="{WIDTH - LEFT}" y="{HEIGHT - 12}" class="micro" text-anchor="end">GITHUB SEARCH · NO PERSONAL ACCESS TOKEN · OWN ORGS EXCLUDED</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--static", action="store_true")
    args = parser.parse_args(argv)
    try:
        ledger = load_ledger(args.input)
        svg = render_svg(ledger, static=args.static)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(svg, encoding="utf-8", newline="\n")
    except (RenderError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output} ({len(svg.encode('utf-8')) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
