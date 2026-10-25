#!/usr/bin/env python3
"""Render the IPL boot-map centrepiece from ``data/profile.json``.

A z/OS-style console brings six subsystems up one line at a time: mark,
subsystem name, address-space id, status light, stack, and a second muted
line with the honest note.  Lines print with the portrait's row wipe; the
light switches on as each line completes; the closing line gives the tally.
Message prefixes are stylised (``MEF``), not real IBM message ids.

    python scripts/make_ipl_svg.py

Contract of ``render_svg(profile) -> str``: pure; raises ValueError on a
profile with fewer than NODE_COUNT flagships.  Stdlib only.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from marks import all_symbols


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "data" / "profile.json"
DEFAULT_OUTPUT = ROOT / "assets" / "ipl-map.svg"

WIDTH = 860
HEIGHT = 420
TITLEBAR_HEIGHT = 30
NODE_COUNT = 6
LEFT = 22
LINE_STEP = 0.42  # seconds between lines
WIPE = 0.32  # seconds per line wipe

STATE_COLOUR = {"up": "#42be65", "research": "#78a9ff", "prealpha": "#f1c21b"}
STATE_LABEL = {"up": "UP", "research": "RESEARCH", "prealpha": "PRE-ALPHA"}


def load_profile(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        profile = json.load(handle)
    flagships = profile.get("flagships")
    if not isinstance(flagships, list) or len(flagships) < NODE_COUNT:
        raise ValueError(f"profile needs at least {NODE_COUNT} flagships")
    for index, project in enumerate(flagships[:NODE_COUNT]):
        for field in ("code", "name", "status", "state", "stack", "mark", "accent", "asid", "note"):
            if not str(project.get(field, "")).strip():
                raise ValueError(f"flagships[{index}] is missing {field}")
        if project["state"] not in STATE_COLOUR:
            raise ValueError(f"flagships[{index}].state must be one of {sorted(STATE_COLOUR)}")
    return profile


def _style(line_count: int) -> str:
    return f"""
          text {{ font-family:'IBM Plex Mono','Cascadia Mono','SFMono-Regular',Consolas,monospace; }}
          .micro {{ fill:#7185a8; font-size:11px; font-weight:600; letter-spacing:1.15px; }}
          .label {{ fill:#78a9ff; font-size:11px; font-weight:700; letter-spacing:1.05px; }}
          .status {{ fill:#42be65; font-size:11px; font-weight:700; letter-spacing:.9px; }}
          .con {{ fill:#d0e2ff; font-size:12px; }}
          .con-id {{ fill:#78a9ff; font-weight:700; }}
          .con-dim {{ fill:#7185a8; }}
          .sub-name {{ fill:#f2f6fc; font-size:12.5px; font-weight:700; }}
          .sub-asid {{ fill:#9fb2d1; font-size:11px; }}
          .sub-state {{ font-size:11px; font-weight:700; letter-spacing:.8px; }}
          .sub-stack {{ fill:#78a9ff; font-size:10.5px; font-weight:600; }}
          .sub-note {{ fill:#7185a8; font-size:10px; }}
          .line {{ transform:scaleX(1); transform-box:fill-box; transform-origin:left center; }}
          .lamp {{ opacity:1; }}
          .lamp-ring {{ opacity:0; }}
          .cursor {{ opacity:0; }}
          @keyframes wipe {{ from {{ transform:scaleX(0); }} to {{ transform:scaleX(1); }} }}
          @keyframes lamp-on {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
          @keyframes lamp-ring {{ 0% {{ opacity:.9; transform:scale(1); }} 100% {{ opacity:0; transform:scale(2.6); }} }}
          @keyframes cursor {{ 0% {{ opacity:.9; transform:translateX(0); }} 90% {{ opacity:.9; transform:translateX(var(--w)); }} 100% {{ opacity:0; transform:translateX(var(--w)); }} }}
          @keyframes blink {{ 0%,49% {{ opacity:1; }} 50%,100% {{ opacity:.16; }} }}
          @media (prefers-reduced-motion:no-preference) {{
            .ipl:not(.static) .line {{ animation:wipe {WIPE}s linear both; animation-delay:var(--t); }}
            .ipl:not(.static) .lamp {{ opacity:0; animation:lamp-on .15s linear forwards; animation-delay:calc(var(--t) + {WIPE}s); }}
            .ipl:not(.static) .lamp-ring {{ transform-box:fill-box; transform-origin:center; animation:lamp-ring .6s ease-out forwards; animation-delay:calc(var(--t) + {WIPE}s); }}
            .ipl:not(.static) .cursor {{ animation:cursor {WIPE}s linear forwards; animation-delay:var(--t); }}
            .ipl:not(.static) .prompt-cursor {{ animation:blink 1.1s step-end 3; animation-delay:{LINE_STEP * line_count + 0.6:.2f}s; }}
          }}
          @media (prefers-reduced-motion:reduce) {{
            .line {{ animation:none !important; transform:scaleX(1) !important; }}
            .lamp {{ animation:none !important; opacity:1 !important; }}
            .lamp-ring, .cursor {{ animation:none !important; opacity:0 !important; }}
            .prompt-cursor {{ animation:none !important; }}
          }}
"""


def render_svg(profile: dict[str, object], *, static: bool = False, today: date | None = None) -> str:
    flagships = profile["flagships"]
    assert isinstance(flagships, list)
    projects = flagships[:NODE_COUNT]
    today = today or date.today()
    root_class = "ipl static" if static else "ipl"
    mark_names = [str(project["mark"]) for project in projects]

    tally: dict[str, int] = {}
    for project in projects:
        tally[str(project["state"])] = tally.get(str(project["state"]), 0) + 1
    tally_text = " · ".join(
        f"{count} {STATE_LABEL[state]}" for state, count in tally.items()
    )

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
            f'aria-labelledby="ipl-title ipl-desc" class="{root_class}" focusable="false">'
        ),
        "<title id=\"ipl-title\">IPL of Mert Efe Şensoy's systems</title>",
        (
            '<desc id="ipl-desc">A stylised mainframe console loads six subsystems, one line each with a '
            "status light and an honest note: "
            + "; ".join(
                f"{escape(str(p['name']))} {STATE_LABEL[str(p['state'])]} ({escape(str(p['status']))}: "
                f"{escape(str(p['note']))})"
                for p in projects
            )
            + f". IPL complete, {escape(tally_text)}.</desc>"
        ),
        "<defs>",
        all_symbols(mark_names),
        '<pattern id="ipl-grid" width="58" height="58" patternUnits="userSpaceOnUse"><path d="M58 0H0V58" fill="none" stroke="#4589ff" stroke-opacity=".04"/></pattern>',
        '<pattern id="ipl-scan" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M0 3.5H860" stroke="#f2f6fc" stroke-opacity=".025"/></pattern>',
    ]

    # Lines: (kind, payload).  Each line gets a clipPath wipe and a start time.
    lines: list[tuple[str, object]] = [
        ("con", f'<tspan class="con-id">MEF001I</tspan> IPL SYS1.MERTEFE · LOADPARM 0A80 · {today.isoformat()}'),
        ("con", '<tspan class="con-id">MEF002I</tspan> MEMBER IEASYS00 FOUND · <tspan class="con-dim">6 SUBSYSTEMS QUEUED</tspan>'),
    ]
    lines.extend(("sub", project) for project in projects)
    lines.append(("con", f'<tspan class="con-id">MEF099I</tspan> IPL COMPLETE · RC=0000 · {escape(tally_text)}'))

    y = TITLEBAR_HEIGHT + 30
    clip_defs: list[str] = []
    body: list[str] = []
    line_index = 0
    for kind, payload in lines:
        start = 0.3 + line_index * LINE_STEP
        if kind == "con":
            height = 20
            clip_defs.append(
                f'<clipPath id="ipl-line-{line_index}"><rect class="line" style="--t:{start:.2f}s" '
                f'x="{LEFT}" y="{y - 14}" width="{WIDTH - 2 * LEFT}" height="{height}"/></clipPath>'
            )
            body.append(
                f'<text x="{LEFT}" y="{y}" class="con" clip-path="url(#ipl-line-{line_index})">{payload}</text>'
            )
            body.append(
                f'<rect class="cursor" style="--t:{start:.2f}s;--w:{WIDTH - 2 * LEFT - 8}px" x="{LEFT}" '
                f'y="{y - 12}" width="7" height="14" fill="#78a9ff"/>'
            )
            y += 24 if line_index > 0 else 22
            if line_index == 1:
                body.append(f'<path d="M{LEFT} {y - 10}H{WIDTH - LEFT}" stroke="#27466f"/>')
                y += 12
        else:
            project = payload
            assert isinstance(project, dict)
            state = str(project["state"])
            colour = STATE_COLOUR[state]
            accent = escape(str(project["accent"]))
            height = 40
            clip_defs.append(
                f'<clipPath id="ipl-line-{line_index}"><rect class="line" style="--t:{start:.2f}s" '
                f'x="{LEFT}" y="{y - 14}" width="{WIDTH - 2 * LEFT}" height="{height}"/></clipPath>'
            )
            body.append(f'<g clip-path="url(#ipl-line-{line_index})">')
            body.append(f'<text x="{LEFT}" y="{y}" class="con" fill="{accent}">▶</text>')
            body.append(
                f'<rect x="{LEFT + 18}" y="{y - 13}" width="26" height="26" rx="2" fill="#07090e" stroke="#1c3153"/>'
                f'<use href="#mark-{escape(str(project["mark"]))}" x="{LEFT + 21}" y="{y - 10}" width="20" height="20"/>'
            )
            body.append(
                f'<text x="{LEFT + 56}" y="{y + 1}" class="sub-name">{escape(str(project["name"]).upper())}</text>'
            )
            body.append(
                f'<text x="{LEFT + 300}" y="{y + 1}" class="sub-asid">ASID {escape(str(project["asid"]))}</text>'
            )
            body.append(
                f'<text x="{LEFT + 408}" y="{y + 1}" class="sub-state" fill="{colour}">{STATE_LABEL[state]}</text>'
            )
            body.append(
                f'<text x="{LEFT + 520}" y="{y + 1}" class="sub-asid">{escape(str(project["status"]).upper())}</text>'
            )
            body.append(
                f'<text x="{WIDTH - LEFT}" y="{y + 1}" class="sub-stack" text-anchor="end">{escape(str(project["stack"]))}</text>'
            )
            body.append(
                f'<text x="{LEFT + 56}" y="{y + 17}" class="sub-note">{escape(str(project["note"]))}</text>'
            )
            body.append("</g>")
            # Status lamp, outside the clip so it can switch on after the wipe.
            body.append(
                f'<circle class="lamp-ring" style="--t:{start:.2f}s" cx="{LEFT + 392}" cy="{y - 3}" r="4" fill="none" stroke="{colour}" stroke-width="1.5"/>'
                f'<circle class="lamp" style="--t:{start:.2f}s" cx="{LEFT + 392}" cy="{y - 3}" r="4" fill="{colour}"/>'
            )
            body.append(
                f'<rect class="cursor" style="--t:{start:.2f}s;--w:{WIDTH - 2 * LEFT - 8}px" x="{LEFT}" '
                f'y="{y - 12}" width="7" height="14" fill="#78a9ff"/>'
            )
            y += 44
        line_index += 1

    parts.extend(clip_defs)
    parts.extend(["<style>", _style(len(lines)), "</style>", "</defs>"])
    parts.extend(
        [
            f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#07090e"/>',
            f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{HEIGHT - 1}" fill="#080e18" stroke="#27466f"/>',
            f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" fill="url(#ipl-grid)"/>',
            f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" fill="url(#ipl-scan)"/>',
            f'<rect x="1" y="1" width="4" height="{HEIGHT - 2}" fill="#4589ff"/>',
            f'<rect x="5" y="1" width="{WIDTH - 6}" height="29" fill="#050a11"/>',
            f'<path d="M5 30H{WIDTH - 1}" stroke="#27466f"/>',
            '<text x="22" y="20" class="label">MERTEFE.SYSPLEX // IPL.CONSOLE</text>',
            '<text x="300" y="20" class="micro">SYSTEM MAP · 6 SUBSYSTEMS</text>',
            '<circle cx="640" cy="15" r="3" fill="#42be65"/>',
            '<text x="651" y="20" class="status">CONSOLE ACTIVE</text>',
            f'<text x="{WIDTH - 22}" y="20" class="micro" text-anchor="end">F1=HELP</text>',
        ]
    )
    parts.extend(body)
    parts.append(
        f'<rect class="prompt-cursor" x="{LEFT}" y="{y - 12}" width="8" height="15" fill="#78a9ff" opacity="0"/>'
    )
    parts.append(
        f'<text x="{WIDTH - LEFT}" y="{HEIGHT - 14}" class="micro" text-anchor="end">STYLISED CONSOLE · MESSAGE IDS ARE NOT IBM\'S</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--static", action="store_true", help="Disable motion")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="Console date (default: today)")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    svg = render_svg(profile, static=args.static, today=args.date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} ({len(svg.encode('utf-8')) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
