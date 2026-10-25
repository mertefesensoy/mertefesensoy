#!/usr/bin/env python3
"""Render the spiking-connectome centrepiece from ``data/profile.json``.

A soma on the left integrates a membrane potential drawn along the bottom.
When the trace crosses threshold the soma fires: one spike rides each axon
to a project node, and the node lights with its own brand mark, accent and an
honest status line.  Farther nodes light later because the spike travels at a
constant speed along a longer axon.  Everything plays once; under reduced
motion the map is shown fully lit with no motion.

    python scripts/make_connectome_svg.py

Contract of ``render_svg(profile) -> str``: pure; raises ValueError when the
profile has fewer than NODE_COUNT flagships or a flagship lacks a field.
Stdlib only, so it can run inside the daily workflow if ever needed.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

from marks import all_symbols


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "data" / "profile.json"
DEFAULT_OUTPUT = ROOT / "assets" / "connectome.svg"

WIDTH = 860
HEIGHT = 500
TITLEBAR_HEIGHT = 30
NODE_COUNT = 6

SOMA_X, SOMA_Y = 165.0, 165.0
SOMA_R = 34.0
CARD_X = 392.0
CARD_W = 444.0
CARD_H = 58.0
CARD_Y0 = 48.0
CARD_PITCH = 66.0

FIRE_AT = 5.6  # seconds; the portrait's three passes take about 6.4 s
SPIKE_SPEED = 420.0  # px per second
TRACE_DURATION = FIRE_AT - 0.1

STATE_COLOUR = {"up": "#42be65", "research": "#78a9ff", "prealpha": "#f1c21b"}
STATE_LABEL = {"up": "UP", "research": "RESEARCH", "prealpha": "PRE-ALPHA"}
REQUIRED = ("code", "name", "status", "state", "stack", "mark", "accent", "tagline", "note")


def load_profile(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        profile = json.load(handle)
    flagships = profile.get("flagships")
    if not isinstance(flagships, list) or len(flagships) < NODE_COUNT:
        raise ValueError(f"profile needs at least {NODE_COUNT} flagships")
    for index, project in enumerate(flagships[:NODE_COUNT]):
        if not isinstance(project, dict):
            raise ValueError(f"flagships[{index}] must be an object")
        missing = [field for field in REQUIRED if not str(project.get(field, "")).strip()]
        if missing:
            raise ValueError(f"flagships[{index}] is missing {', '.join(missing)}")
        if project["state"] not in STATE_COLOUR:
            raise ValueError(f"flagships[{index}].state must be one of {sorted(STATE_COLOUR)}")
    return profile


def _fit(text: str, width_px: float, char_px: float) -> str:
    """Truncate ``text`` with an ellipsis so it fits ``width_px`` at ``char_px`` per glyph."""

    limit = max(1, int(width_px // char_px))
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _cubic(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1.0 - t
    x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
    return x, y


def axon(index: int) -> tuple[str, float]:
    """Return the axon path for node ``index`` and its length in px."""

    end_y = CARD_Y0 + index * CARD_PITCH + CARD_H / 2
    p0 = (SOMA_X + SOMA_R, SOMA_Y)
    p1 = (SOMA_X + SOMA_R + 110, SOMA_Y)
    p2 = (CARD_X - 90, end_y)
    p3 = (CARD_X - 6, end_y)
    length = 0.0
    previous = p0
    for step in range(1, 65):
        point = _cubic(p0, p1, p2, p3, step / 64)
        length += math.hypot(point[0] - previous[0], point[1] - previous[1])
        previous = point
    path = (
        f"M{p0[0]:.1f} {p0[1]:.1f} C{p1[0]:.1f} {p1[1]:.1f} {p2[0]:.1f} {p2[1]:.1f} "
        f"{p3[0]:.1f} {p3[1]:.1f}"
    )
    return path, length


def membrane_trace() -> tuple[str, float]:
    """A leaky-integrate-and-fire style V_m trace in the scope box."""

    x0, x1 = 34.0, 372.0
    base_y, threshold_y = 440.0, 346.0
    points: list[tuple[float, float]] = []
    steps = 72
    for step in range(steps + 1):
        s = step / steps
        # Slow leaky rise with small input bumps, then the crossing.
        rise = 1.0 - math.exp(-3.2 * s)
        bump = 0.045 * math.sin(s * 31.0) * (1.0 - s)
        level = min(1.0, rise + bump + 0.08 * s)
        y = base_y - level * (base_y - threshold_y) * 0.985
        points.append((x0 + (x1 - x0) * s * 0.9, y))
    # The spike: straight up past threshold, straight back down below rest.
    spike_x = points[-1][0]
    points.append((spike_x + 2, threshold_y - 44))
    points.append((spike_x + 6, base_y + 8))
    points.append((x1, base_y - 4))
    length = 0.0
    for a, b in zip(points, points[1:]):
        length += math.hypot(b[0] - a[0], b[1] - a[1])
    path = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points)
    return path, length


def _style(nodes: list[tuple[float, float]], trace_length: float) -> str:
    node_rules = "\n".join(
        f"          .node-{index} {{ --arrive:{FIRE_AT + length / SPIKE_SPEED:.2f}s; }}"
        for index, (_, length) in enumerate(nodes)
    )
    return f"""
          text {{ font-family:'IBM Plex Mono','Cascadia Mono','SFMono-Regular',Consolas,monospace; }}
          .micro {{ fill:#7185a8; font-size:11px; font-weight:600; letter-spacing:1.15px; }}
          .label {{ fill:#78a9ff; font-size:11px; font-weight:700; letter-spacing:1.05px; }}
          .status {{ fill:#42be65; font-size:11px; font-weight:700; letter-spacing:.9px; }}
          .node-name {{ fill:#f2f6fc; font-size:13px; font-weight:700; }}
          .node-code {{ fill:#7185a8; font-size:10px; font-weight:600; letter-spacing:1px; }}
          .node-tag {{ fill:#9fb2d1; font-size:10px; }}
          .node-note {{ fill:#7185a8; font-size:9.5px; }}
          .node-stack {{ fill:#78a9ff; font-size:9.5px; font-weight:600; letter-spacing:.6px; }}
          .pill {{ font-size:9px; font-weight:700; letter-spacing:.8px; }}
          .soma-label {{ fill:#f2f6fc; font-size:12px; font-weight:700; }}
          .scope-label {{ fill:#7185a8; font-size:10px; font-weight:600; letter-spacing:1px; }}
          .axon {{ fill:none; stroke:#27466f; stroke-width:1.4; }}
          .axon-charge {{ fill:none; stroke-width:1.8; stroke-linecap:round; }}
          .trace {{ fill:none; stroke:#78a9ff; stroke-width:1.6; stroke-linejoin:round; }}
          .node {{ opacity:1; }}
          .node-glow {{ opacity:.9; }}
          .fired {{ opacity:1; }}
          .armed {{ opacity:0; }}
          .soma-flash {{ opacity:0; }}
          .spike {{ opacity:0; }}
{node_rules}
          @keyframes light {{ from {{ opacity:.28; }} to {{ opacity:1; }} }}
          @keyframes glow {{ from {{ opacity:0; }} to {{ opacity:.9; }} }}
          @keyframes charge {{ to {{ stroke-dashoffset:0; }} }}
          @keyframes draw {{ to {{ stroke-dashoffset:0; }} }}
          @keyframes flash {{ 0% {{ opacity:.9; transform:scale(1); }} 100% {{ opacity:0; transform:scale(2.1); }} }}
          @keyframes swap-out {{ to {{ opacity:0; }} }}
          @keyframes swap-in {{ to {{ opacity:1; }} }}
          @keyframes spike-vis {{ 0% {{ opacity:1; }} 100% {{ opacity:1; }} }}
          @media (prefers-reduced-motion:no-preference) {{
            .connectome:not(.static) .node {{ opacity:.28; animation:light .35s ease-out forwards; animation-delay:var(--arrive); }}
            .connectome:not(.static) .node-glow {{ opacity:0; animation:glow .5s ease-out forwards; animation-delay:var(--arrive); }}
            .connectome:not(.static) .axon-charge {{ stroke-dashoffset:var(--len); animation:charge var(--dur) linear forwards; animation-delay:{FIRE_AT}s; }}
            .connectome:not(.static) .trace {{ stroke-dasharray:{trace_length:.0f}; stroke-dashoffset:{trace_length:.0f}; animation:draw {TRACE_DURATION:.1f}s linear forwards; }}
            .connectome:not(.static) .soma-flash {{ transform-box:fill-box; transform-origin:center; animation:flash .7s ease-out forwards; animation-delay:{FIRE_AT}s; }}
            .connectome:not(.static) .armed {{ opacity:1; animation:swap-out .01s linear forwards; animation-delay:{FIRE_AT + 1.4:.1f}s; }}
            .connectome:not(.static) .fired {{ opacity:0; animation:swap-in .01s linear forwards; animation-delay:{FIRE_AT + 1.4:.1f}s; }}
            .connectome:not(.static) .spike {{ animation:spike-vis var(--dur) linear forwards; animation-delay:{FIRE_AT}s; }}
          }}
          @media (prefers-reduced-motion:reduce) {{
            .node, .node-glow, .fired {{ animation:none !important; opacity:1 !important; }}
            .armed, .spike, .soma-flash {{ animation:none !important; opacity:0 !important; display:none; }}
            .axon-charge {{ animation:none !important; stroke-dashoffset:0 !important; }}
            .trace {{ animation:none !important; stroke-dashoffset:0 !important; }}
          }}
          .connectome.static .spike, .connectome.static .armed, .connectome.static .soma-flash {{ display:none; }}
"""


def render_svg(profile: dict[str, object], *, static: bool = False) -> str:
    flagships = profile["flagships"]
    assert isinstance(flagships, list)
    nodes = [axon(index) for index in range(NODE_COUNT)]
    trace_path, trace_length = membrane_trace()
    root_class = "connectome static" if static else "connectome"
    mark_names = [str(project["mark"]) for project in flagships[:NODE_COUNT]]

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
            f'aria-labelledby="connectome-title connectome-desc" class="{root_class}" focusable="false">'
        ),
        "<title id=\"connectome-title\">Mert Efe Şensoy's project connectome</title>",
        (
            '<desc id="connectome-desc">A soma labelled mertefe integrates a membrane potential, crosses '
            "threshold and fires one spike along six axons. Each spike lights a project node with its brand "
            "mark and an honest status line: "
            + "; ".join(
                f"{escape(str(p['name']))} ({escape(str(p['status']))}: {escape(str(p['tagline']))})"
                for p in flagships[:NODE_COUNT]
            )
            + ".</desc>"
        ),
        "<defs>",
        all_symbols(mark_names),
        '<pattern id="cx-grid" width="58" height="58" patternUnits="userSpaceOnUse"><path d="M58 0H0V58" fill="none" stroke="#4589ff" stroke-opacity=".04"/></pattern>',
        '<pattern id="cx-scan" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M0 3.5H860" stroke="#f2f6fc" stroke-opacity=".025"/></pattern>',
        '<radialGradient id="cx-soma"><stop offset="0" stop-color="#f8f1e0"/><stop offset=".45" stop-color="#78a9ff"/><stop offset="1" stop-color="#0f1f3d"/></radialGradient>',
    ]
    for index, (path, _) in enumerate(nodes):
        parts.append(f'<path id="axon-{index}" d="{path}"/>')
    parts.extend(
        [
            "<style>",
            _style(nodes, trace_length),
            "</style>",
            "</defs>",
            f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#07090e"/>',
            f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{HEIGHT - 1}" fill="#080e18" stroke="#27466f"/>',
            f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" fill="url(#cx-grid)"/>',
            f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" fill="url(#cx-scan)"/>',
            f'<rect x="1" y="1" width="4" height="{HEIGHT - 2}" fill="#4589ff"/>',
            f'<rect x="5" y="1" width="{WIDTH - 6}" height="29" fill="#050a11"/>',
            f'<path d="M5 30H{WIDTH - 1}" stroke="#27466f"/>',
            '<text x="22" y="20" class="label">MERTEFE.SYSPLEX // CONNECTOME.MAP</text>',
            '<text x="330" y="20" class="micro">1 SOMA · 6 AXONS · LIF MODEL</text>',
            '<g class="armed"><circle cx="640" cy="15" r="3" fill="#f1c21b"/>'
            '<text x="651" y="20" class="status" fill="#f1c21b">SPIKE ARMED</text></g>',
            '<g class="fired"><circle cx="640" cy="15" r="3" fill="#42be65"/>'
            '<text x="651" y="20" class="status">FIRED · 6/6 LIT</text></g>',
            f'<text x="{WIDTH - 22}" y="20" class="micro" text-anchor="end">F1=HELP</text>',
        ]
    )

    # Axons, resting and charging.
    for index, (path, length) in enumerate(nodes):
        accent = escape(str(flagships[index]["accent"]))
        duration = length / SPIKE_SPEED
        parts.append(f'<use href="#axon-{index}" class="axon"/>')
        parts.append(
            f'<use href="#axon-{index}" class="axon-charge" stroke="{accent}" '
            f'stroke-dasharray="{length:.0f}" style="--len:{length:.0f};--dur:{duration:.2f}s"/>'
        )

    # Soma.
    parts.extend(
        [
            f'<circle class="soma-flash" cx="{SOMA_X}" cy="{SOMA_Y}" r="{SOMA_R}" fill="none" stroke="#f8f1e0" stroke-width="2"/>',
            f'<circle cx="{SOMA_X}" cy="{SOMA_Y}" r="{SOMA_R + 10}" fill="none" stroke="#27466f" stroke-dasharray="3 5"/>',
            f'<circle cx="{SOMA_X}" cy="{SOMA_Y}" r="{SOMA_R}" fill="url(#cx-soma)" stroke="#78a9ff" stroke-width="1.5"/>',
            f'<circle cx="{SOMA_X}" cy="{SOMA_Y}" r="9" fill="#f8f1e0"/>',
            f'<text x="{SOMA_X}" y="{SOMA_Y + SOMA_R + 30}" class="soma-label" text-anchor="middle">mertefe</text>',
            f'<text x="{SOMA_X}" y="{SOMA_Y + SOMA_R + 46}" class="micro" text-anchor="middle">SOMA · SYSTEMS ENGINEER</text>',
            # Dendrites: three inputs from the left, the sources of the integration.
            f'<path d="M{SOMA_X - SOMA_R:.0f} {SOMA_Y:.0f} C{SOMA_X - 70:.0f} {SOMA_Y:.0f} {SOMA_X - 60:.0f} {SOMA_Y - 62:.0f} {SOMA_X - 86:.0f} {SOMA_Y - 66:.0f}" class="axon"/>',
            f'<path d="M{SOMA_X - SOMA_R:.0f} {SOMA_Y:.0f} C{SOMA_X - 60:.0f} {SOMA_Y:.0f} {SOMA_X - 70:.0f} {SOMA_Y:.0f} {SOMA_X - 86:.0f} {SOMA_Y:.0f}" class="axon"/>',
            f'<path d="M{SOMA_X - SOMA_R:.0f} {SOMA_Y:.0f} C{SOMA_X - 70:.0f} {SOMA_Y:.0f} {SOMA_X - 60:.0f} {SOMA_Y + 62:.0f} {SOMA_X - 86:.0f} {SOMA_Y + 66:.0f}" class="axon"/>',
            f'<circle cx="{SOMA_X - 86:.0f}" cy="{SOMA_Y - 66:.0f}" r="2.5" fill="#27466f"/>',
            f'<circle cx="{SOMA_X - 86:.0f}" cy="{SOMA_Y:.0f}" r="2.5" fill="#27466f"/>',
            f'<circle cx="{SOMA_X - 86:.0f}" cy="{SOMA_Y + 66:.0f}" r="2.5" fill="#27466f"/>',
            f'<text x="22" y="{SOMA_Y - 62:.0f}" class="micro">IBM Z</text>',
            f'<text x="22" y="{SOMA_Y + 4:.0f}" class="micro">QUANTUM</text>',
            f'<text x="22" y="{SOMA_Y + 70:.0f}" class="micro">HARDWARE</text>',
        ]
    )

    # Membrane scope.
    parts.extend(
        [
            '<rect x="24" y="300" width="356" height="150" fill="#050a11" stroke="#27466f"/>',
            '<text x="34" y="316" class="scope-label">V_m · SOMA · LEAKY INTEGRATE-AND-FIRE</text>',
            '<path d="M34 346H372" stroke="#f1c21b" stroke-dasharray="4 4" stroke-opacity=".7"/>',
            '<text x="372" y="341" class="scope-label" text-anchor="end" fill="#f1c21b">THRESHOLD</text>',
            '<path d="M34 440H372" stroke="#27466f"/>',
            '<text x="34" y="436" class="scope-label">REST</text>',
            f'<path d="{trace_path}" class="trace"/>',
            f'<text x="372" y="462" class="micro" text-anchor="end">t = {FIRE_AT:.1f}s · FIRE</text>',
        ]
    )

    # Nodes.
    for index, project in enumerate(flagships[:NODE_COUNT]):
        path, length = nodes[index]
        y = CARD_Y0 + index * CARD_PITCH
        accent = escape(str(project["accent"]))
        state = str(project["state"])
        colour = STATE_COLOUR[state]
        duration = length / SPIKE_SPEED
        status_raw = str(project["status"]).upper()
        pill_w = 6.6 * len(status_raw) + 16
        status = escape(status_raw)
        text_x = CARD_X + 60
        text_w = CARD_W - 72
        tagline = escape(_fit(str(project["tagline"]), text_w, 6.0))
        note = escape(_fit(str(project["note"]), text_w, 5.75))
        parts.append(f'<g class="node node-{index}">')
        parts.append(
            f'<rect x="{CARD_X}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="2" fill="#0b1422" stroke="#27466f"/>'
        )
        parts.append(
            f'<rect class="node-glow" x="{CARD_X}" y="{y}" width="3" height="{CARD_H}" fill="{accent}"/>'
        )
        parts.append(f'<circle cx="{CARD_X - 6}" cy="{y + CARD_H / 2}" r="3.5" fill="{accent}"/>')
        parts.append(
            f'<rect x="{CARD_X + 12}" y="{y + 11}" width="36" height="36" rx="3" fill="#07090e" stroke="#1c3153"/>'
        )
        parts.append(
            f'<use href="#mark-{escape(str(project["mark"]))}" x="{CARD_X + 16}" y="{y + 15}" width="28" height="28"/>'
        )
        parts.append(
            f'<text x="{CARD_X + 60}" y="{y + 22}" class="node-name">{escape(str(project["name"]))}'
            f'<tspan class="node-code" dx="8">{escape(str(project["code"]))}</tspan></text>'
        )
        parts.append(
            f'<rect x="{CARD_X + CARD_W - pill_w - 12}" y="{y + 10}" width="{pill_w:.0f}" height="16" rx="2" '
            f'fill="#07090e" stroke="{colour}"/>'
            f'<circle cx="{CARD_X + CARD_W - pill_w - 4}" cy="{y + 18}" r="2.5" fill="{colour}"/>'
            f'<text x="{CARD_X + CARD_W - pill_w + 4}" y="{y + 21.5}" class="pill" fill="{colour}">{status}</text>'
        )
        parts.append(f'<text x="{text_x}" y="{y + 37}" class="node-tag">{tagline}</text>')
        parts.append(f'<text x="{text_x}" y="{y + 50}" class="node-note">{note}</text>')
        parts.append("</g>")
        # The spike riding this axon (SMIL motion; hidden under reduced motion by CSS).
        parts.append(
            f'<circle class="spike" r="3.2" fill="{accent}" style="--dur:{duration:.2f}s">'
            f'<animateMotion begin="{FIRE_AT}s" dur="{duration:.2f}s" fill="freeze" rotate="auto">'
            f'<mpath href="#axon-{index}"/></animateMotion></circle>'
        )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--static", action="store_true", help="Disable motion")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    svg = render_svg(profile, static=args.static)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} ({len(svg.encode('utf-8')) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
