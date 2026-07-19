#!/usr/bin/env python3
"""Render normalized contribution data as a compact IBM/Carbon SVG."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from html import escape
from pathlib import Path
from typing import Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "contributions.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "contrib-heatmap.svg"

WIDTH = 888
HEIGHT = 166
WEEKS = 53
CELL_SIZE = 13
CELL_GAP = 3
CELL_PITCH = CELL_SIZE + CELL_GAP
CALENDAR_X = 34
CALENDAR_Y = 28

BACKGROUND = "#07090e"
PANEL = "#080e18"
BORDER = "#1c3153"
LEVEL_COLORS = ("#161b22", "#1c3153", "#054ada", "#4589ff", "#78a9ff")
TEXT = "#f2f6fc"
MUTED_TEXT = "#9fb2d1"
SUBTLE_TEXT = "#7185a8"
STATUS_GREEN = "#42be65"
FLASH = "#a6c8ff"


class RenderError(RuntimeError):
    """Raised when contribution JSON is invalid or cannot be rendered."""


@dataclass(frozen=True)
class RenderDay:
    day: date
    count: int
    level: int


@dataclass(frozen=True)
class ContributionDocument:
    username: str
    generated_at: str
    days: tuple[RenderDay, ...]
    stats: Mapping[str, object]


def _nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RenderError(f"{field} must be a non-negative integer")
    return value


def load_contribution_data(path: Path) -> ContributionDocument:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RenderError(f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise RenderError(f"unable to read {path}: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RenderError("unsupported or missing contribution schema_version")
    username = payload.get("username")
    generated_at = payload.get("generated_at")
    if not isinstance(username, str) or not username.strip():
        raise RenderError("username must be a non-empty string")
    if not isinstance(generated_at, str) or not generated_at:
        raise RenderError("generated_at must be a non-empty string")

    raw_days = payload.get("days")
    if not isinstance(raw_days, list) or not raw_days:
        raise RenderError("days must be a non-empty array")
    seen_dates: set[date] = set()
    days: list[RenderDay] = []
    for index, raw_day in enumerate(raw_days):
        if not isinstance(raw_day, dict):
            raise RenderError(f"days[{index}] must be an object")
        raw_date = raw_day.get("date")
        if not isinstance(raw_date, str):
            raise RenderError(f"days[{index}].date must be an ISO date")
        try:
            parsed_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise RenderError(f"invalid date {raw_date!r} at days[{index}]") from exc
        if parsed_date in seen_dates:
            raise RenderError(f"duplicate date {raw_date!r}")
        seen_dates.add(parsed_date)
        count = _nonnegative_integer(raw_day.get("count"), f"days[{index}].count")
        level = _nonnegative_integer(raw_day.get("level"), f"days[{index}].level")
        if level > 4 or (count == 0) != (level == 0):
            raise RenderError(f"days[{index}] has inconsistent count/level data")
        days.append(RenderDay(parsed_date, count, level))
    days.sort(key=lambda item: item.day)

    stats = payload.get("stats")
    if not isinstance(stats, dict):
        raise RenderError("stats must be an object")
    yearly_total = _nonnegative_integer(stats.get("yearly_total"), "stats.yearly_total")
    if yearly_total != sum(item.count for item in days):
        raise RenderError("stats.yearly_total does not match the sum of day counts")
    _nonnegative_integer(stats.get("current_streak"), "stats.current_streak")
    _nonnegative_integer(stats.get("longest_streak"), "stats.longest_streak")
    return ContributionDocument(username.strip(), generated_at, tuple(days), stats)


def _sunday_index(day: date) -> int:
    return (day.weekday() + 1) % 7


def _display_bounds(days: Sequence[RenderDay]) -> tuple[date, date]:
    display_end = max(item.day for item in days)
    display_start = display_end - timedelta(
        days=(WEEKS - 1) * 7 + _sunday_index(display_end)
    )
    return display_start, display_end


def _visible_days(
    days: Sequence[RenderDay], display_start: date, display_end: date
) -> list[RenderDay]:
    by_date = {item.day: item for item in days}
    cursor = max(min(by_date), display_start)
    visible: list[RenderDay] = []
    while cursor <= display_end:
        visible.append(by_date.get(cursor, RenderDay(cursor, 0, 0)))
        cursor += timedelta(days=1)
    return visible


def _month_positions(
    visible: Sequence[RenderDay], display_start: date
) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    seen: set[tuple[int, int]] = set()
    for item in visible:
        key = (item.day.year, item.day.month)
        if key in seen:
            continue
        seen.add(key)
        week = (item.day - display_start).days // 7
        candidates.append((week, item.day.strftime("%b").upper()))
    positions: list[tuple[int, str]] = []
    for candidate in candidates:
        if positions and candidate[0] - positions[-1][0] < 3:
            if positions[-1][0] == 0:
                positions[-1] = candidate
            continue
        positions.append(candidate)
    return positions


def _text(
    x: int | float,
    y: int | float,
    value: str,
    class_name: str,
    *,
    anchor: str | None = None,
) -> str:
    anchor_attribute = f' text-anchor="{anchor}"' if anchor else ""
    return (
        f'<text x="{x}" y="{y}" class="{class_name}"{anchor_attribute}>'
        f'{escape(value)}</text>'
    )


def render_svg(document: ContributionDocument) -> str:
    display_start, display_end = _display_bounds(document.days)
    visible_days = _visible_days(document.days, display_start, display_end)
    yearly_total = _nonnegative_integer(document.stats.get("yearly_total"), "stats.yearly_total")
    current_streak = _nonnegative_integer(document.stats.get("current_streak"), "stats.current_streak")
    longest_streak = _nonnegative_integer(document.stats.get("longest_streak"), "stats.longest_streak")

    title = f"{document.username}'s 53-week GitHub contribution signal"
    description = (
        f"Contribution calendar from {max(min(item.day for item in document.days), display_start)} "
        f"through {display_end}, totaling {yearly_total:,} contributions. "
        f"Current streak: {current_streak} days; longest streak: {longest_streak} days."
    )
    max_order = (WEEKS - 1) + 6 * 0.55

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
            'aria-labelledby="calendar-title calendar-desc" focusable="false">'
        ),
        f'<title id="calendar-title">{escape(title)}</title>',
        f'<desc id="calendar-desc">{escape(description)}</desc>',
        '<defs><pattern id="heatmap-scan" width="4" height="4" patternUnits="userSpaceOnUse"><path d="M0 3.5H888" stroke="#f2f6fc" stroke-opacity=".018"/></pattern></defs>',
        '<style>',
        "text { font-family:'IBM Plex Mono','IBM Plex Sans',ui-monospace,SFMono-Regular,Consolas,monospace; }",
        f'.axis {{ fill:{SUBTLE_TEXT}; font-size:9px; font-weight:600; letter-spacing:.45px; }}',
        f'.footer {{ fill:{MUTED_TEXT}; font-size:10px; font-weight:600; letter-spacing:.35px; }}',
        f'.footer-value {{ fill:{TEXT}; font-size:11px; font-weight:700; }}',
        f'.ready {{ fill:{STATUS_GREEN}; }}',
        '.contribution-cell { opacity:1; transform:none; transform-box:fill-box; transform-origin:center; }',
        '@keyframes cell-in { 0% { opacity:0; transform:scale(.2); } 60% { opacity:1; transform:scale(1.1); } 100% { opacity:1; transform:scale(1); } }',
        f'@keyframes cell-flash {{ 0%,45% {{ filter:brightness(2.25) drop-shadow(0 0 2px {FLASH}); }} 100% {{ filter:brightness(1) drop-shadow(0 0 0 transparent); }} }}',
        '@media (prefers-reduced-motion: no-preference) {',
        '  .contribution-cell { opacity:0; animation: cell-in .55s ease-out both; animation-delay:var(--delay); }',
        '  .contribution-cell.active { animation: cell-in .55s ease-out both,cell-flash .70s ease-out both; animation-delay:var(--delay),var(--delay); }',
        '}',
        '@media (prefers-reduced-motion: reduce) { .contribution-cell { opacity:1 !important; animation:none !important; transform:none !important; filter:none !important; } }',
        '</style>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{BACKGROUND}"/>',
        f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{HEIGHT - 1}" fill="{PANEL}" stroke="{BORDER}"/>',
        '<rect x="1" y="1" width="3" height="164" fill="#4589ff"/>',
        '<rect x="1" y="1" width="886" height="164" fill="url(#heatmap-scan)"/>',
    ]

    for week, label in _month_positions(visible_days, display_start):
        lines.append(_text(CALENDAR_X + week * CELL_PITCH, 18, label, "axis"))
    for row, label in ((1, "MON"), (3, "WED"), (5, "FRI")):
        lines.append(
            _text(
                CALENDAR_X - 5,
                CALENDAR_Y + row * CELL_PITCH + CELL_SIZE - 2,
                label,
                "axis",
                anchor="end",
            )
        )

    lines.append('<g aria-label="Contribution calendar, Sunday through Saturday">')
    for item in visible_days:
        offset = (item.day - display_start).days
        week = offset // 7
        row = _sunday_index(item.day)
        if not 0 <= week < WEEKS:
            continue
        x = CALENDAR_X + week * CELL_PITCH
        y = CALENDAR_Y + row * CELL_PITCH
        level = min(item.level, 4)
        color = LEVEL_COLORS[level]
        order = week + row * 0.55
        delay = order / max_order * 3.6
        state_class = " active" if item.count > 0 else ""
        label = (
            f"{item.count:,} contribution{'s' if item.count != 1 else ''} on "
            f"{item.day.strftime('%B %d, %Y')}"
            if item.count
            else f"No contributions on {item.day.strftime('%B %d, %Y')}"
        )
        lines.extend(
            [
                (
                    f'<rect class="contribution-cell level-{level}{state_class}" '
                    f'x="{x}" y="{y}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="2" '
                    f'fill="{color}" data-date="{item.day.isoformat()}" data-count="{item.count}" '
                    f'style="--delay:{delay:.3f}s">'
                ),
                f'<title>{escape(label)}</title>',
                '</rect>',
            ]
        )
    lines.append('</g>')

    lines.extend(
        [
            f'<path d="M4 144H887" stroke="{BORDER}"/>',
            '<circle cx="18" cy="155" r="3" fill="#42be65"/>',
            _text(29, 159, f"{yearly_total:,} CONTRIBUTIONS / LAST 12 MONTHS", "footer-value"),
            _text(
                876,
                159,
                f"CURRENT {current_streak}D  ·  LONGEST {longest_streak}D  ·  UPDATED {display_end.strftime('%d %b').upper()}",
                "footer",
                anchor="end",
            ),
            '</svg>',
        ]
    )
    return "\n".join(lines) + "\n"


def write_text_atomic(contents: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            'w',
            encoding='utf-8',
            newline='\n',
            dir=output.parent,
            prefix=f'.{output.name}.',
            suffix='.tmp',
            delete=False,
        ) as temporary:
            temporary.write(contents)
            temporary_name = temporary.name
        os.replace(temporary_name, output)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Render contribution JSON as a compact animated IBM/Carbon SVG.'
    )
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        document = load_contribution_data(args.input)
        svg = render_svg(document)
        write_text_atomic(svg, args.output)
    except (RenderError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {WIDTH}x{HEIGHT} contribution SVG to {args.output}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
