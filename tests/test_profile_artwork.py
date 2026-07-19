from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from validate_profile import validate_svg  # noqa: E402


class ProfileArtworkContractTests(unittest.TestCase):
    def test_three_assets_keep_reference_shaped_proportions(self) -> None:
        assets = (
            (REPOSITORY_ROOT / "assets" / "mert-ascii.svg", 840, 875),
            (REPOSITORY_ROOT / "assets" / "info-card.svg", 480, 376),
            (REPOSITORY_ROOT / "contrib-heatmap.svg", 888, 166),
        )
        for path, width, height in assets:
            with self.subTest(path=path.name):
                root = validate_svg(path, expected_width=width)
                self.assertEqual(root.attrib["height"], str(height))

    def test_portrait_has_one_row_and_cursor_per_ascii_line(self) -> None:
        source = (REPOSITORY_ROOT / "assets" / "mert-ascii.svg").read_text(
            encoding="utf-8"
        )
        self.assertEqual(source.count('class="ascii-row"'), 64)
        self.assertEqual(source.count('class="row-cursor"'), 64)
        self.assertEqual(source.count('<clipPath id="portrait-row-'), 64)
        root = ET.fromstring(source)
        rows = [
            "".join(node.itertext())
            for node in root.iter()
            if node.attrib.get("class") == "ascii-row"
        ]
        self.assertEqual({len(row) for row in rows}, {120})
        visible_glyphs = set("".join(rows)) - {" "}
        self.assertGreaterEqual(len(visible_glyphs), 10)
        density = sum(character != " " for row in rows for character in row) / (
            len(rows) * 120
        )
        self.assertGreater(density, 0.32)
        self.assertLess(density, 0.52)
        self.assertIn("animation:sweep-cursor .09s", source)
        self.assertIn("prefers-reduced-motion:reduce", source)
        self.assertNotIn("infinite", source)

    def test_info_card_and_heatmap_keep_one_shot_motion_contracts(self) -> None:
        card = (REPOSITORY_ROOT / "assets" / "info-card.svg").read_text(
            encoding="utf-8"
        )
        heatmap = (REPOSITORY_ROOT / "contrib-heatmap.svg").read_text(
            encoding="utf-8"
        )
        self.assertEqual(card.count('class="card-row"'), 13)
        self.assertIn("animation:card-row-in .40s", card)
        self.assertNotIn("infinite", card)
        self.assertIn("animation: cell-in .55s", heatmap)
        self.assertIn("cell-flash .70s", heatmap)
        self.assertNotIn("infinite", heatmap)
        ET.fromstring(card)
        ET.fromstring(heatmap)


if __name__ == "__main__":
    unittest.main()
