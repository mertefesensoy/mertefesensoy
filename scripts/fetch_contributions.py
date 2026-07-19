#!/usr/bin/env python3
"""Fetch and normalize GitHub's public contribution calendar.

The public contribution fragment does not require a token.  GitHub exposes the
date and intensity on each calendar cell and the exact count in the cell's
associated ``<tool-tip>`` element.  This module intentionally uses only the
Python standard library so the daily profile workflow stays small and stable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "data" / "contributions.json"
DEFAULT_USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER", "mertefesensoy")
CONTRIBUTIONS_URL = "https://github.com/users/{username}/contributions"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MIN_CALENDAR_DAYS = 364
MAX_CALENDAR_DAYS = 371
USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
COUNT_RE = re.compile(r"(?<!\d)([\d,]+)\s+contributions?\b", re.IGNORECASE)
NO_CONTRIBUTIONS_RE = re.compile(r"\bno\s+contributions?\b", re.IGNORECASE)


class ContributionError(RuntimeError):
    """Base error for contribution fetch and parse failures."""


class ContributionParseError(ContributionError):
    """Raised when GitHub's fragment cannot be interpreted safely."""


@dataclass(frozen=True, order=True)
class ContributionDay:
    """A single day from the GitHub contribution calendar."""

    date: date
    count: int
    level: int

    def as_json(self) -> dict[str, object]:
        return {
            "date": self.date.isoformat(),
            "count": self.count,
            "level": self.level,
        }


@dataclass
class _RawCell:
    day: date
    level: int
    cell_id: str | None
    inline_labels: list[str]
    explicit_count: int | None = None


class _ContributionFragmentParser(HTMLParser):
    """Collect contribution cells and their separately rendered tooltips."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: dict[date, _RawCell] = {}
        self.tooltips: dict[str, str] = {}
        self._last_cell_id: str | None = None
        self._tooltip_target: str | None = None
        self._tooltip_chunks: list[str] = []
        self._tooltip_nesting = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._handle_open_tag(tag, attrs)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._handle_open_tag(tag, attrs)
        if tag.lower() == "tool-tip":
            self._finish_tooltip()

    def _handle_open_tag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.lower()
        attr_map = {key.lower(): value for key, value in attrs}

        if tag == "tool-tip":
            # A missing ``for`` is not current GitHub markup, but associating it
            # with the immediately preceding cell makes the parser tolerant of
            # a harmless markup simplification.
            self._tooltip_target = attr_map.get("for") or self._last_cell_id
            self._tooltip_chunks = []
            self._tooltip_nesting = 0
            return

        if self._tooltip_target is not None:
            self._tooltip_nesting += 1

        raw_date = attr_map.get("data-date")
        raw_level = attr_map.get("data-level")
        if raw_date is None or raw_level is None:
            return

        try:
            cell_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ContributionParseError(
                f"invalid contribution date {raw_date!r}"
            ) from exc

        try:
            level = int(raw_level)
        except ValueError as exc:
            raise ContributionParseError(
                f"invalid contribution level {raw_level!r} for {raw_date}"
            ) from exc
        if not 0 <= level <= 4:
            raise ContributionParseError(
                f"contribution level {level} outside 0..4 for {raw_date}"
            )

        cell_id = attr_map.get("id")
        labels = [
            label
            for label in (attr_map.get("aria-label"), attr_map.get("title"))
            if label
        ]
        explicit_count = None
        if attr_map.get("data-count") is not None:
            explicit_count = _parse_integer(attr_map["data-count"] or "")

        existing = self.cells.get(cell_date)
        if existing is not None:
            if (
                existing.level != level
                or existing.cell_id != cell_id
                or existing.explicit_count != explicit_count
            ):
                raise ContributionParseError(
                    f"conflicting duplicate contribution cell for {raw_date}"
                )
            existing.inline_labels.extend(labels)
        else:
            self.cells[cell_date] = _RawCell(
                day=cell_date,
                level=level,
                cell_id=cell_id,
                inline_labels=labels,
                explicit_count=explicit_count,
            )
        self._last_cell_id = cell_id

    def handle_data(self, data: str) -> None:
        if self._tooltip_target is not None:
            self._tooltip_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._tooltip_target is None:
            return
        if tag.lower() == "tool-tip" and self._tooltip_nesting == 0:
            self._finish_tooltip()
        elif self._tooltip_nesting:
            self._tooltip_nesting -= 1

    def close(self) -> None:
        super().close()
        if self._tooltip_target is not None:
            # Preserve useful data from a fragment truncated immediately after
            # tooltip text, while still letting missing positive counts fail in
            # the validation step below.
            self._finish_tooltip()

    def _finish_tooltip(self) -> None:
        if self._tooltip_target:
            text = " ".join("".join(self._tooltip_chunks).split())
            if text:
                previous = self.tooltips.get(self._tooltip_target)
                if previous and previous != text:
                    raise ContributionParseError(
                        f"conflicting tooltips for cell {self._tooltip_target!r}"
                    )
                self.tooltips[self._tooltip_target] = text
        self._tooltip_target = None
        self._tooltip_chunks = []
        self._tooltip_nesting = 0


def _parse_integer(value: str) -> int:
    normalized = value.replace(",", "").strip()
    if not normalized.isdigit():
        raise ContributionParseError(f"invalid contribution count {value!r}")
    return int(normalized)


def _count_from_label(label: str) -> int | None:
    if NO_CONTRIBUTIONS_RE.search(label):
        return 0
    match = COUNT_RE.search(label)
    return _parse_integer(match.group(1)) if match else None


def parse_contributions_html(fragment: str) -> list[ContributionDay]:
    """Parse GitHub's public contribution fragment into sorted day records.

    Zero-level cells without a tooltip are safely interpreted as zero.  A
    positive-level cell without an exact count is rejected instead of silently
    inventing a number from its relative color level.
    """

    parser = _ContributionFragmentParser()
    try:
        parser.feed(fragment)
        parser.close()
    except ContributionParseError:
        raise
    except Exception as exc:  # HTMLParser errors are rare, keep the CLI useful.
        raise ContributionParseError(f"unable to parse contribution HTML: {exc}") from exc

    if not parser.cells:
        raise ContributionParseError(
            "no data-date/data-level contribution cells found; GitHub markup may have changed"
        )

    parsed: list[ContributionDay] = []
    for cell in sorted(parser.cells.values(), key=lambda item: item.day):
        candidates: list[int] = []
        if cell.explicit_count is not None:
            candidates.append(cell.explicit_count)
        for label in cell.inline_labels:
            count = _count_from_label(label)
            if count is not None:
                candidates.append(count)
        if cell.cell_id and cell.cell_id in parser.tooltips:
            count = _count_from_label(parser.tooltips[cell.cell_id])
            if count is not None:
                candidates.append(count)

        if len(set(candidates)) > 1:
            raise ContributionParseError(
                f"conflicting contribution counts for {cell.day.isoformat()}"
            )
        if candidates:
            count = candidates[0]
        elif cell.level == 0:
            count = 0
        else:
            raise ContributionParseError(
                "missing exact tooltip count for positive contribution cell "
                f"{cell.day.isoformat()}"
            )
        if count < 0:
            raise ContributionParseError(
                f"negative contribution count for {cell.day.isoformat()}"
            )
        if (count == 0) != (cell.level == 0):
            raise ContributionParseError(
                "inconsistent contribution count/level for "
                f"{cell.day.isoformat()}: count={count}, level={cell.level}"
            )
        parsed.append(ContributionDay(cell.day, count, cell.level))

    return parsed


def validate_complete_calendar(days: Sequence[ContributionDay]) -> None:
    """Reject partial or structurally inconsistent annual calendars."""

    day_count = len(days)
    if not MIN_CALENDAR_DAYS <= day_count <= MAX_CALENDAR_DAYS:
        raise ContributionParseError(
            "expected a complete GitHub calendar with "
            f"{MIN_CALENDAR_DAYS}..{MAX_CALENDAR_DAYS} days; received {day_count}"
        )

    seen_dates: set[date] = set()
    previous_date: date | None = None
    for index, item in enumerate(days):
        if item.date in seen_dates:
            raise ContributionParseError(
                f"duplicate contribution date {item.date.isoformat()}"
            )
        seen_dates.add(item.date)

        if not 0 <= item.level <= 4:
            raise ContributionParseError(
                f"contribution level {item.level} outside 0..4 for {item.date.isoformat()}"
            )
        if item.count < 0 or (item.count == 0) != (item.level == 0):
            raise ContributionParseError(
                "inconsistent contribution count/level for "
                f"{item.date.isoformat()}: count={item.count}, level={item.level}"
            )

        if previous_date is not None:
            if item.date <= previous_date:
                raise ContributionParseError(
                    f"contribution calendar is not sorted at index {index}"
                )
            expected_date = previous_date + timedelta(days=1)
            if item.date != expected_date:
                raise ContributionParseError(
                    "contribution calendar contains a gap: expected "
                    f"{expected_date.isoformat()}, found {item.date.isoformat()}"
                )
        previous_date = item.date


def calculate_stats(days: Sequence[ContributionDay]) -> dict[str, object]:
    """Calculate annual total, streaks, best day, and calendar-month totals."""

    if not days:
        return {
            "yearly_total": 0,
            "current_streak": 0,
            "longest_streak": 0,
            "best_day": None,
            "monthly_totals": {},
        }

    by_date: dict[date, ContributionDay] = {}
    for item in days:
        if item.date in by_date:
            raise ValueError(f"duplicate contribution date {item.date.isoformat()}")
        by_date[item.date] = item

    first_day = min(by_date)
    last_day = max(by_date)
    yearly_total = sum(item.count for item in by_date.values())

    longest_streak = 0
    running_streak = 0
    cursor = first_day
    monthly_totals: OrderedDict[str, int] = OrderedDict()
    while cursor <= last_day:
        count = by_date.get(cursor, ContributionDay(cursor, 0, 0)).count
        month_key = cursor.strftime("%Y-%m")
        monthly_totals.setdefault(month_key, 0)
        monthly_totals[month_key] += count
        if count > 0:
            running_streak += 1
            longest_streak = max(longest_streak, running_streak)
        else:
            running_streak = 0
        cursor += timedelta(days=1)

    # Give today's still-open cell a one-day grace period.  This matches how a
    # "current" habit streak is normally presented: yesterday's streak remains
    # current until the latest calendar day is complete.
    streak_cursor = last_day
    if by_date[last_day].count == 0:
        streak_cursor -= timedelta(days=1)
    current_streak = 0
    while streak_cursor >= first_day:
        item = by_date.get(streak_cursor)
        if item is None or item.count == 0:
            break
        current_streak += 1
        streak_cursor -= timedelta(days=1)

    contributing_days = [item for item in by_date.values() if item.count > 0]
    best = (
        max(contributing_days, key=lambda item: (item.count, item.date))
        if contributing_days
        else None
    )

    return {
        "yearly_total": yearly_total,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "best_day": (
            {"date": best.date.isoformat(), "count": best.count} if best else None
        ),
        "monthly_totals": dict(monthly_totals),
    }


def fetch_contributions_html(username: str, timeout: float = 30.0) -> str:
    """Download a user's public contribution fragment without authentication."""

    if not USERNAME_RE.fullmatch(username):
        raise ContributionError(f"invalid GitHub username {username!r}")

    url = CONTRIBUTIONS_URL.format(username=username)
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "mertefesensoy-profile-readme/1.0 (+https://github.com/mertefesensoy)",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS host
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ContributionError("GitHub contribution response exceeded 5 MiB")
            charset = response.headers.get_content_charset() or "utf-8"
    except HTTPError as exc:
        raise ContributionError(
            f"GitHub returned HTTP {exc.code} for {username!r}"
        ) from exc
    except URLError as exc:
        raise ContributionError(f"unable to reach GitHub: {exc.reason}") from exc

    try:
        return body.decode(charset)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ContributionError(
            f"unable to decode GitHub response as {charset}"
        ) from exc


def build_payload(
    username: str,
    days: Sequence[ContributionDay],
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Build the stable JSON document consumed by the SVG renderer."""

    validate_complete_calendar(days)
    ordered_days = list(days)
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    generated_at = generated_at.astimezone(timezone.utc).replace(microsecond=0)

    return {
        "schema_version": 1,
        "username": username,
        "source": CONTRIBUTIONS_URL.format(username=username),
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "range": {
            "start": ordered_days[0].date.isoformat(),
            "end": ordered_days[-1].date.isoformat(),
            "days": len(ordered_days),
        },
        "stats": calculate_stats(ordered_days),
        "days": [item.as_json() for item in ordered_days],
    }


def write_json_atomic(payload: Mapping[str, object], output: Path) -> None:
    """Write JSON atomically so a failed refresh cannot truncate profile data."""

    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary_name = temporary.name
        os.replace(temporary_name, output)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch GitHub's public contribution calendar as normalized JSON."
    )
    parser.add_argument(
        "username",
        nargs="?",
        default=DEFAULT_USERNAME,
        help=f"GitHub username (default: {DEFAULT_USERNAME})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"JSON output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--html-file",
        type=Path,
        help="parse a saved contribution fragment instead of making a network request",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        fragment = (
            args.html_file.read_text(encoding="utf-8")
            if args.html_file
            else fetch_contributions_html(args.username)
        )
        days = parse_contributions_html(fragment)
        payload = build_payload(args.username, days)
        write_json_atomic(payload, args.output)
    except (ContributionError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stats = payload["stats"]
    assert isinstance(stats, dict)
    print(
        f"wrote {len(days)} days / {stats['yearly_total']:,} contributions "
        f"to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
