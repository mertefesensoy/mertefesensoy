from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPOSITORY_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from fetch_contributions import (  # noqa: E402
    ContributionDay,
    ContributionParseError,
    build_payload,
    calculate_stats,
    parse_contributions_html,
)
from render_heatmap_svg import (  # noqa: E402
    ContributionDocument,
    HEIGHT,
    LEVEL_COLORS,
    RenderDay,
    WIDTH,
    render_svg,
)


FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "contributions_fragment.html"


def _complete_calendar(length: int = 365) -> list[ContributionDay]:
    start = date(2025, 1, 1)
    return [
        ContributionDay(start + timedelta(days=offset), 0, 0)
        for offset in range(length)
    ]


class ContributionParserTests(unittest.TestCase):
    def test_parses_current_cells_and_associated_tooltip_counts(self) -> None:
        days = parse_contributions_html(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(
            [(item.date.isoformat(), item.count, item.level) for item in days],
            [
                ("2026-01-01", 0, 0),
                ("2026-01-02", 1, 1),
                ("2026-01-03", 1_234, 4),
                ("2026-01-04", 7, 2),
                ("2026-01-05", 0, 0),
            ],
        )

    def test_rejects_positive_cell_when_exact_count_is_missing(self) -> None:
        fragment = '<td data-date="2026-01-01" data-level="2" id="day"></td>'
        with self.assertRaisesRegex(ContributionParseError, "missing exact tooltip count"):
            parse_contributions_html(fragment)

    def test_rejects_markup_without_contribution_cells(self) -> None:
        with self.assertRaisesRegex(ContributionParseError, "no data-date/data-level"):
            parse_contributions_html("<p>GitHub returned a login page</p>")

    def test_rejects_contribution_level_outside_github_range(self) -> None:
        fragment = '<td data-date="2026-01-01" data-level="5" data-count="1"></td>'
        with self.assertRaisesRegex(ContributionParseError, "outside 0..4"):
            parse_contributions_html(fragment)

    def test_rejects_inconsistent_zero_count_and_level(self) -> None:
        fragments = (
            '<td data-date="2026-01-01" data-level="1" data-count="0"></td>',
            '<td data-date="2026-01-01" data-level="0" data-count="2"></td>',
        )
        for fragment in fragments:
            with self.subTest(fragment=fragment):
                with self.assertRaisesRegex(ContributionParseError, "inconsistent"):
                    parse_contributions_html(fragment)


class ContributionStatsTests(unittest.TestCase):
    def test_calculates_total_streaks_best_day_and_months(self) -> None:
        days = [
            ContributionDay(date(2026, 1, 30), 1, 1),
            ContributionDay(date(2026, 1, 31), 2, 2),
            ContributionDay(date(2026, 2, 1), 0, 0),
            ContributionDay(date(2026, 2, 2), 3, 3),
            ContributionDay(date(2026, 2, 3), 5, 4),
            ContributionDay(date(2026, 2, 4), 0, 0),
        ]

        stats = calculate_stats(days)

        self.assertEqual(stats["yearly_total"], 11)
        self.assertEqual(stats["current_streak"], 2)
        self.assertEqual(stats["longest_streak"], 2)
        self.assertEqual(stats["best_day"], {"date": "2026-02-03", "count": 5})
        self.assertEqual(stats["monthly_totals"], {"2026-01": 3, "2026-02": 8})

    def test_missing_calendar_date_breaks_a_streak(self) -> None:
        days = [
            ContributionDay(date(2026, 1, 1), 2, 2),
            ContributionDay(date(2026, 1, 3), 2, 2),
        ]
        stats = calculate_stats(days)
        self.assertEqual(stats["longest_streak"], 1)
        self.assertEqual(stats["current_streak"], 1)

    def test_build_payload_has_stable_schema(self) -> None:
        days = _complete_calendar()
        payload = build_payload(
            "mertefesensoy",
            days,
            generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["generated_at"], "2026-01-02T03:04:05Z")
        self.assertEqual(
            payload["range"], {"start": "2025-01-01", "end": "2025-12-31", "days": 365}
        )


class CompleteCalendarValidationTests(unittest.TestCase):
    def test_rejects_truncated_and_oversized_calendars(self) -> None:
        for length in (363, 372):
            with self.subTest(length=length):
                with self.assertRaisesRegex(ContributionParseError, "364..371"):
                    build_payload("mertefesensoy", _complete_calendar(length))

    def test_rejects_unsorted_dates(self) -> None:
        days = _complete_calendar()
        days[0], days[1] = days[1], days[0]
        with self.assertRaisesRegex(ContributionParseError, "not sorted"):
            build_payload("mertefesensoy", days)

    def test_rejects_duplicate_dates(self) -> None:
        days = _complete_calendar()
        days[1] = days[0]
        with self.assertRaisesRegex(ContributionParseError, "duplicate"):
            build_payload("mertefesensoy", days)

    def test_rejects_calendar_gap(self) -> None:
        days = _complete_calendar()
        original = days[100]
        days[100] = ContributionDay(original.date + timedelta(days=1), 0, 0)
        with self.assertRaisesRegex(ContributionParseError, "contains a gap"):
            build_payload("mertefesensoy", days)

    def test_rejects_invalid_constructed_level_semantics(self) -> None:
        invalid_days = (
            ContributionDay(date(2025, 1, 11), 0, 1),
            ContributionDay(date(2025, 1, 11), 1, 0),
            ContributionDay(date(2025, 1, 11), 1, 5),
        )
        for invalid_day in invalid_days:
            days = _complete_calendar()
            days[10] = invalid_day
            with self.subTest(day=invalid_day):
                with self.assertRaises(ContributionParseError):
                    build_payload("mertefesensoy", days)


class HeatmapRendererTests(unittest.TestCase):
    def _document(self):
        start = date(2025, 7, 20)  # Sunday, matching a complete 53-column window.
        days = [
            ContributionDay(
                start + timedelta(days=offset),
                0 if offset % 5 == 0 else (offset % 9) + 1,
                0 if offset % 5 == 0 else (offset % 4) + 1,
            )
            for offset in range(365)
        ]
        generated_at = datetime(2026, 7, 19, 6, 17, tzinfo=timezone.utc)
        payload = build_payload(
            "mertefesensoy",
            days,
            generated_at=generated_at,
        )
        return ContributionDocument(
            username="mertefesensoy",
            generated_at=payload["generated_at"],
            days=tuple(RenderDay(item.date, item.count, item.level) for item in days),
            stats=payload["stats"],
        )

    def test_renders_accessible_self_contained_animated_svg(self) -> None:
        document = self._document()
        svg = render_svg(document)
        root = ET.fromstring(svg)

        self.assertEqual(root.attrib["width"], str(WIDTH))
        self.assertEqual(root.attrib["height"], str(HEIGHT))
        self.assertEqual(root.attrib["role"], "img")
        self.assertEqual(root.attrib["aria-labelledby"], "calendar-title calendar-desc")
        self.assertIn("prefers-reduced-motion: reduce", svg)
        self.assertIn("animation: cell-in", svg)
        self.assertNotIn("infinite", svg)
        self.assertNotIn("<script", svg.lower())
        self.assertNotIn("http://", svg.replace('xmlns="http://www.w3.org/2000/svg"', ""))
        self.assertEqual(svg.count('class="contribution-cell'), 365)
        for color in LEVEL_COLORS:
            self.assertIn(color, svg)
        for color in ("#07090e", "#080e18", "#f2f6fc", "#9fb2d1", "#7185a8", "#42be65"):
            self.assertIn(color, svg)

    def test_last_day_lands_in_the_53rd_sunday_column(self) -> None:
        document = self._document()
        root = ET.fromstring(render_svg(document))
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        target = next(
            node
            for node in root.findall(".//svg:rect", namespace)
            if node.attrib.get("data-date") == "2026-07-19"
        )
        self.assertEqual(target.attrib["x"], "866")
        self.assertEqual(target.attrib["y"], "28")


if __name__ == "__main__":
    unittest.main()
