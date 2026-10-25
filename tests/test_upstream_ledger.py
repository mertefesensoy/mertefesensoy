from __future__ import annotations

import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from fetch_upstream_prs import build_payload, normalize  # noqa: E402
from render_ledger_svg import RenderError, load_ledger, render_svg  # noqa: E402
from validate_profile import ProfileValidationError, validate_ledger_data  # noqa: E402


FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "search_prs_fragment.json"


def fixture_items() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]


class UpstreamLedgerTests(unittest.TestCase):
    def test_normalize_filters_own_orgs_and_duplicates(self) -> None:
        records = normalize(fixture_items())
        keys = [(r["repo"], r["number"], r["state"]) for r in records]
        self.assertEqual(
            keys,
            [
                ("microsoft/vcpkg", 54529, "merged"),
                ("zowe/zowe-mcp", 127, "merged"),
                ("zowe/zowe-cli", 2980, "open"),
                ("unitaryfoundation/mitiq", 3169, "closed"),
            ],
        )
        self.assertEqual(records[0]["merged"], "2026-10-21")
        self.assertIsNone(records[2]["merged"])

    def test_payload_counts_sorts_and_records_caveats(self) -> None:
        payload = build_payload(
            "mertefesensoy",
            normalize(fixture_items()),
            generated_at=datetime(2026, 10, 25, 6, 17, tzinfo=timezone.utc),
        )
        self.assertEqual(payload["generated_at"], "2026-10-25T06:17:00Z")
        self.assertEqual(
            payload["stats"],
            {"merged": 2, "open": 1, "closed": 1, "repositories": 4, "last_merged": "2026-10-21"},
        )
        self.assertEqual(
            [entry["repo"] for entry in payload["repositories"]],
            ["microsoft/vcpkg", "zowe/zowe-mcp", "zowe/zowe-cli", "unitaryfoundation/mitiq"],
        )
        self.assertEqual([r["number"] for r in payload["merged"]], [54529, 127])
        self.assertEqual([r["number"] for r in payload["open"]], [2980])
        self.assertIn("cassandra-collective", payload["excluded_owners"])
        self.assertTrue(any("1000" in caveat for caveat in payload["caveats"]))

    def test_payload_passes_validation_and_renders(self) -> None:
        payload = build_payload("mertefesensoy", normalize(fixture_items()))
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            path = Path(temporary) / "upstream_prs.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            validate_ledger_data(path)
            svg = render_svg(load_ledger(path))
        root = ET.fromstring(svg)
        self.assertEqual(root.attrib["width"], "860")
        self.assertEqual(root.attrib["role"], "img")
        self.assertIn("2 merged, 1 open, across 4 repositories", svg)
        self.assertIn("microsoft/vcpkg#54529", svg)
        self.assertNotIn("infinite", svg)
        self.assertIn("prefers-reduced-motion:reduce", svg)

    def test_validation_rejects_tally_mismatch_and_excluded_owner(self) -> None:
        payload = build_payload("mertefesensoy", normalize(fixture_items()))
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            path = Path(temporary) / "upstream_prs.json"
            broken = json.loads(json.dumps(payload))
            broken["stats"]["merged"] = 9
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaisesRegex(ProfileValidationError, "per-repository tally"):
                validate_ledger_data(path)
            leaked = json.loads(json.dumps(payload))
            leaked["repositories"].append({"repo": "mertefesensoy/FlyBatch", "merged": 0, "open": 0, "closed": 0})
            leaked["stats"]["repositories"] += 1
            path.write_text(json.dumps(leaked), encoding="utf-8")
            with self.assertRaisesRegex(ProfileValidationError, "excluded owner"):
                validate_ledger_data(path)

    def test_renderer_rejects_wrong_schema(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            path = Path(temporary) / "bad.json"
            path.write_text('{"schema_version": 2}', encoding="utf-8")
            with self.assertRaises(RenderError):
                load_ledger(path)

    def test_committed_ledger_is_valid(self) -> None:
        validate_ledger_data(REPOSITORY_ROOT / "data" / "upstream_prs.json")


if __name__ == "__main__":
    unittest.main()
