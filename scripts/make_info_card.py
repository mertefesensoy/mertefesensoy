#!/usr/bin/env python3
"""Render the IBM-styled neofetch companion card for the profile portrait.

The row-model architecture is inspired by AVIVASHISHTA29's public profile,
while the implementation, content model, visual system, and motion fallback
are original to this repository.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "data" / "profile.json"
DEFAULT_OUTPUT = ROOT / "assets" / "info-card.svg"

WIDTH = 480
HEIGHT = 376
PADDING = 20
TITLEBAR_HEIGHT = 30
KEY_X = PADDING
VALUE_X = 108
LINE_HEIGHT = 20.4


def load_profile(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        profile = json.load(handle)
    required = {
        "username",
        "display_name",
        "now",
        "recognition",
        "education",
        "focus",
        "stack_groups",
        "flagships",
    }
    missing = sorted(required - profile.keys())
    if missing:
        raise ValueError(f"Missing profile fields: {', '.join(missing)}")
    if not isinstance(profile["stack_groups"], list) or len(profile["stack_groups"]) < 3:
        raise ValueError("stack_groups must contain at least three rows")
    if not isinstance(profile["flagships"], list) or len(profile["flagships"]) < 3:
        raise ValueError("flagships must contain at least three projects")
    return profile


def _group(inner: str, index: int) -> str:
    delay = 0.15 + index * 0.06
    return f'<g class="card-row" style="--delay:{delay:.2f}s">{inner}</g>'


def render_svg(profile: dict[str, object], *, static: bool = False) -> str:
    stack_groups = profile["stack_groups"]
    projects = profile["flagships"]
    assert isinstance(stack_groups, list)
    assert isinstance(projects, list)

    rows: list[tuple[str, str, str] | tuple[str, str] | tuple[str]] = [
        ("host",),
        ("kv", "Now", str(profile["now"])),
        ("kv", "IBM", str(profile["recognition"])),
        ("kv", "Edu", "TEDU CENG '27 · BA minor"),
        ("kv", "Focus", str(profile["focus"])),
        ("gap",),
        ("section", "Stack"),
    ]
    for group in stack_groups[:3]:
        if not isinstance(group, dict):
            raise ValueError("Each stack_groups entry must be an object")
        rows.append(("kv", str(group["label"]), str(group["value"])))
    rows.extend([("gap",), ("section", "Active channels")])
    for project in projects[:3]:
        if not isinstance(project, dict):
            raise ValueError("Each flagships entry must be an object")
        rows.append(("bullet", f'{project["code"]} // {project["status"]}'))

    root_class = "info-card static" if static else "info-card"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
            f'aria-labelledby="info-title info-desc" class="{root_class}" focusable="false">'
        ),
        '<title id="info-title">Mert Efe Şensoy — IBM neofetch profile card</title>',
        (
            '<desc id="info-desc">Current role, IBM recognition, education, focus areas, '
            'technical stack, and active projects shown as a compact system status card.</desc>'
        ),
        '<defs>',
        '<pattern id="info-grid" width="58" height="58" patternUnits="userSpaceOnUse"><path d="M58 0H0V58" fill="none" stroke="#4589ff" stroke-opacity=".04"/></pattern>',
        '<pattern id="info-scan" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M0 3.5H480" stroke="#f2f6fc" stroke-opacity=".025"/></pattern>',
        '</defs>',
        '<style>',
        """
          text { font-family:'IBM Plex Mono','Cascadia Mono','SFMono-Regular',Consolas,monospace; }
          .title { fill:#78a9ff; font-size:10px; font-weight:700; letter-spacing:1.05px; }
          .micro { fill:#7185a8; font-size:9px; font-weight:600; letter-spacing:1px; }
          .host { fill:#f2f6fc; font-size:14px; font-weight:700; }
          .host-accent { fill:#78a9ff; }
          .key { fill:#78a9ff; font-size:11.5px; font-weight:700; }
          .value { fill:#f2f6fc; font-size:11.5px; font-weight:500; }
          .section { fill:#a6c8ff; font-size:10.5px; font-weight:700; letter-spacing:.8px; }
          .bullet { fill:#9fb2d1; font-size:11.5px; font-weight:500; }
          .status { fill:#42be65; font-size:9px; font-weight:700; letter-spacing:.75px; }
          .card-row { opacity:1; transform:none; }
          @keyframes card-row-in {
            from { opacity:0; transform:translateY(5px); }
            to { opacity:1; transform:translateY(0); }
          }
          @media (prefers-reduced-motion:no-preference) {
            .info-card:not(.static) .card-row {
              animation:card-row-in .40s cubic-bezier(.2,.8,.2,1) both;
              animation-delay:var(--delay);
            }
          }
          @media (prefers-reduced-motion:reduce) {
            .card-row { animation:none !important; opacity:1 !important; transform:none !important; }
          }
        """,
        '</style>',
        '<rect width="480" height="376" fill="#07090e"/>',
        '<rect x=".5" y=".5" width="479" height="375" fill="#080e18" stroke="#27466f"/>',
        '<rect x="1" y="1" width="478" height="374" fill="url(#info-grid)"/>',
        '<rect x="1" y="1" width="478" height="374" fill="url(#info-scan)"/>',
        '<rect x="1" y="1" width="4" height="374" fill="#4589ff"/>',
        '<rect x="5" y="1" width="474" height="29" fill="#050a11"/>',
        '<path d="M5 30H479" stroke="#27466f"/>',
        '<text x="20" y="20" class="title">SDSF // IDENTITY.DATA</text>',
        '<circle cx="369" cy="15" r="3" fill="#42be65"/>',
        '<text x="380" y="20" class="status">READY</text>',
        '<text x="460" y="20" class="micro" text-anchor="end">F1=HELP</text>',
    ]

    y = TITLEBAR_HEIGHT + 27
    visible_index = 0
    for row in rows:
        kind = row[0]
        if kind == "gap":
            y += LINE_HEIGHT * 0.40
            continue
        if kind == "host":
            username = escape(str(profile["username"]))
            inner = (
                f'<text x="{KEY_X}" y="{y:.1f}" class="host"><tspan class="host-accent">'
                f'{username}</tspan><tspan fill="#7185a8">@</tspan>sysplex</text>'
                f'<path d="M168 {y - 4:.1f}H460" stroke="#1c3153"/>'
            )
        elif kind == "section":
            title = escape(row[1].upper())
            rule_start = min(430, KEY_X + 22 + len(row[1]) * 7.2)
            inner = (
                f'<text x="{KEY_X}" y="{y:.1f}" class="section">— {title}</text>'
                f'<path d="M{rule_start:.1f} {y - 4:.1f}H460" stroke="#1c3153"/>'
            )
        elif kind == "kv":
            inner = (
                f'<text x="{KEY_X}" y="{y:.1f}" class="key">{escape(row[1])}</text>'
                f'<text x="{VALUE_X}" y="{y:.1f}" class="value">{escape(row[2])}</text>'
            )
        elif kind == "bullet":
            inner = (
                f'<rect x="{KEY_X}" y="{y - 10:.1f}" width="3" height="12" fill="#4589ff"/>'
                f'<text x="{KEY_X + 13}" y="{y:.1f}" class="bullet">{escape(row[1])}</text>'
            )
        else:
            raise ValueError(f"Unsupported row type: {kind}")
        parts.append(_group(inner, visible_index))
        visible_index += 1
        y += LINE_HEIGHT

    parts.extend(
        [
            '<path d="M5 347H479" stroke="#27466f"/>',
            '<text x="20" y="366" class="micro">F3=PROJECTS   F6=CONTACT</text>',
            '<text x="460" y="366" class="status" text-anchor="end">RC=0000</text>',
            '</svg>',
        ]
    )
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--static", action="store_true", help="Disable entrance animations")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    svg = render_svg(profile, static=args.static)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
