from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from fetch_contributions import ContributionDay, build_payload  # noqa: E402
from update_readme_stats import (  # noqa: E402
    END_MARKER,
    START_MARKER,
    StatsUpdateError,
    build_summary,
    load_contribution_summary,
    replace_stats_block,
    update_readme,
)
from validate_profile import (  # noqa: E402
    ProfileValidationError,
    readme_image_sources,
    validate_contribution_data,
    validate_identity_data,
    validate_readme_images,
    validate_svg,
)


def contribution_payload() -> dict[str, object]:
    end = date(2026, 1, 5)
    start = end - timedelta(days=364)
    counts = [0] * 360 + [0, 2, 3, 0, 5]
    days = [
        ContributionDay(start + timedelta(days=index), count, 0 if count == 0 else 1)
        for index, count in enumerate(counts)
    ]
    return build_payload(
        "mertefesensoy",
        days,
        generated_at=datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc),
    )


def profile_payload() -> dict[str, object]:
    return {
        "username": "mertefesensoy",
        "display_name": "Mert Efe Şensoy",
        "headline": "Systems Engineer",
        "kicker": "SYSTEMS · QUANTUM",
        "now": "Junior Data Analyst",
        "recognition": "IBM Champion",
        "education": "TED UNIVERSITY",
        "roles": ["IBM Champion", "Student Ambassador"],
        "focus": "Systems",
        "stack": "Python · C",
        "stack_groups": [
            {"label": "Systems", "value": "C · Rust"},
            {"label": "Research", "value": "Python · Qiskit"},
            {"label": "Hardware", "value": "KiCad · DDR4"},
        ],
        "endpoint": "mertefesensoy.dev",
        "flagships": [
            {"code": "OMI", "name": "Open Memory", "status": "ACTIVE", "stack": "Rust"},
            {"code": "SCTD", "name": "Quantum", "status": "RESEARCH", "stack": "Qiskit"},
            {"code": "MŞHT", "name": "Müşahit", "status": "OPERATIONAL", "stack": "Python"},
        ],
    }


def accessible_svg(extra: str = "", *, width: str = "860") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" role="img" '
        'aria-labelledby="asset-title asset-desc">'
        '<title id="asset-title">Profile art</title>'
        '<desc id="asset-desc">An accessible description.</desc>'
        f"{extra}</svg>"
    )


class ReadmeStatsTests(unittest.TestCase):
    def test_replaces_only_marker_interior_with_one_line_summary(self) -> None:
        original = f"before\n{START_MARKER}\nold\ncontent\n{END_MARKER}\nafter\n"
        summary = "One accessible line."
        updated = replace_stats_block(original, summary)
        self.assertEqual(
            updated,
            f"before\n{START_MARKER}\n{summary}\n{END_MARKER}\nafter\n",
        )

    def test_rejects_missing_duplicate_or_reversed_markers(self) -> None:
        invalid_readmes = (
            "no markers",
            f"{START_MARKER}\n{START_MARKER}\n{END_MARKER}",
            f"{START_MARKER}\n{END_MARKER}\n{END_MARKER}",
            f"{END_MARKER}\n{START_MARKER}",
        )
        for readme in invalid_readmes:
            with self.subTest(readme=readme), self.assertRaises(StatsUpdateError):
                replace_stats_block(readme, "summary")

    def test_updates_from_json_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            directory = Path(temporary)
            data_path = directory / "contributions.json"
            readme_path = directory / "README.md"
            data_path.write_text(json.dumps(contribution_payload()), encoding="utf-8")
            readme_path.write_text(
                f"# Profile\n\n{START_MARKER}\nold\n{END_MARKER}\n", encoding="utf-8"
            )

            self.assertTrue(update_readme(data_path, readme_path))
            self.assertFalse(update_readme(data_path, readme_path))
            result = readme_path.read_text(encoding="utf-8")
            summary_line = result.splitlines()[3]
            self.assertIn("Total: 10 contributions", summary_line)
            self.assertIn("Current streak: 1 day", summary_line)
            self.assertIn("Longest streak: 2 days", summary_line)
            self.assertIn("Best day: 5 contributions on 2026-01-05", summary_line)
            self.assertIn("Generated: 2026-01-06", summary_line)

    def test_summary_loader_rejects_boolean_integer(self) -> None:
        payload = contribution_payload()
        payload["stats"]["yearly_total"] = True  # type: ignore[index]
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            path = Path(temporary) / "data.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(StatsUpdateError, "yearly_total"):
                load_contribution_summary(path)


class ProfileValidatorTests(unittest.TestCase):
    def test_validates_complete_json_contracts(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            directory = Path(temporary)
            contributions = directory / "contributions.json"
            profile = directory / "profile.json"
            contributions.write_text(json.dumps(contribution_payload()), encoding="utf-8")
            profile.write_text(json.dumps(profile_payload()), encoding="utf-8")
            validate_contribution_data(contributions)
            validate_identity_data(profile)

    def test_rejects_inconsistent_derived_stats(self) -> None:
        payload = contribution_payload()
        payload["stats"]["yearly_total"] = 999  # type: ignore[index]
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            path = Path(temporary) / "contributions.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ProfileValidationError, "derived contribution stats"):
                validate_contribution_data(path)

    def test_rejects_inconsistent_count_and_level(self) -> None:
        payload = contribution_payload()
        payload["days"][0]["level"] = 1  # type: ignore[index]
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            path = Path(temporary) / "contributions.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ProfileValidationError, "inconsistent"):
                validate_contribution_data(path)

    def test_rejects_short_or_nonconsecutive_calendars(self) -> None:
        for label, mutate in (
            ("short", lambda days: days[:363]),
            (
                "gap",
                lambda days: days[:100]
                + days[101:]
                + [
                    {
                        "date": "2026-01-06",
                        "count": 0,
                        "level": 0,
                    }
                ],
            ),
        ):
            payload = contribution_payload()
            payload["days"] = mutate(payload["days"])  # type: ignore[arg-type]
            payload["range"]["days"] = len(payload["days"])  # type: ignore[index,arg-type]
            payload["range"]["end"] = payload["days"][-1]["date"]  # type: ignore[index]
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
                    path = Path(temporary) / "contributions.json"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(
                        ProfileValidationError, "calendar records|consecutive"
                    ):
                        validate_contribution_data(path)

    def test_accepts_860_and_860px_accessible_svgs(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            path = Path(temporary) / "asset.svg"
            for width in ("860", "860px", "860.0px"):
                with self.subTest(width=width):
                    path.write_text(accessible_svg(width=width), encoding="utf-8")
                    validate_svg(path)

    def test_rejects_active_and_external_svg_content(self) -> None:
        cases = {
            "script": "<script>alert(1)</script>",
            "foreignObject": "<foreignObject><p>HTML</p></foreignObject>",
            "event handler": '<rect onload="alert(1)"/>',
            "external href": '<image href="https://example.com/a.png"/>',
            "external CSS": '<style>.x { fill: url(https://example.com/a.svg); }</style>',
        }
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            path = Path(temporary) / "asset.svg"
            for label, content in cases.items():
                with self.subTest(label=label):
                    path.write_text(accessible_svg(content), encoding="utf-8")
                    with self.assertRaises(ProfileValidationError):
                        validate_svg(path)

    def test_readme_local_image_resolution(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            root = Path(temporary)
            asset = root / "assets" / "identity.svg"
            asset.parent.mkdir()
            asset.write_text("svg", encoding="utf-8")
            readme = root / "README.md"
            readme.write_text(
                "![Identity](./assets/identity.svg)\n"
                '<img src="https://example.com/remote.svg" alt="remote">\n',
                encoding="utf-8",
            )
            self.assertEqual(validate_readme_images(readme), [asset.resolve()])

            readme.write_text("![Missing](./missing.svg)\n", encoding="utf-8")
            with self.assertRaisesRegex(ProfileValidationError, "do not exist"):
                validate_readme_images(readme)


if __name__ == "__main__":
    unittest.main()
