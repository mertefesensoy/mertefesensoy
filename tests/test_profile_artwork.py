from __future__ import annotations

import json
import re
import sys
import unittest
from datetime import date
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

try:  # The portrait renderer needs Pillow and NumPy, which the daily workflow does not install.
    import make_ascii_svg  # noqa: E402
except ImportError:  # pragma: no cover - exercised in CI
    make_ascii_svg = None  # type: ignore[assignment]
import make_connectome_svg  # noqa: E402
import make_ipl_svg  # noqa: E402
from marks import MARKS, all_symbols, symbol  # noqa: E402
from validate_profile import validate_svg  # noqa: E402


ASSETS = REPOSITORY_ROOT / "assets"
TAG_RE = re.compile(r"<[^>]+>")
# The committed portrait's grid; checked from the SVG text so this runs without Pillow.
PORTRAIT_COLS = 150
PORTRAIT_ROWS = 80


def _ascii_rows(source: str) -> list[str]:
    rows: list[str] = []
    for match in re.finditer(r'<text[^>]*class="ascii-row"[^>]*>(.*?)</text>', source, re.S):
        rows.append(TAG_RE.sub("", match.group(1)))
    return rows


class ProfileArtworkContractTests(unittest.TestCase):
    def test_assets_keep_their_fixed_sizes(self) -> None:
        assets = (
            (ASSETS / "mert-ascii.svg", 840, 875),
            (ASSETS / "info-card.svg", 480, 376),
            (REPOSITORY_ROOT / "contrib-heatmap.svg", 888, 166),
            (ASSETS / "connectome.svg", 860, 500),
            (ASSETS / "ipl-map.svg", 860, 420),
            (ASSETS / "pr-ledger.svg", 860, 340),
        )
        for path, width, height in assets:
            with self.subTest(path=path.name):
                root = validate_svg(path, expected_width=width)
                self.assertEqual(root.attrib["height"], str(height))

    def test_portrait_grid_tiers_passes_and_edges(self) -> None:
        source = (ASSETS / "mert-ascii.svg").read_text(encoding="utf-8")
        rows = _ascii_rows(source)
        self.assertEqual(len(rows), PORTRAIT_ROWS)
        self.assertEqual(
            {len(row.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")) for row in rows},
            {PORTRAIT_COLS},
        )
        # One sweep cursor per row per pass.
        self.assertEqual(source.count('class="row-cursor cursor-a"'), PORTRAIT_ROWS)
        self.assertEqual(source.count('class="row-cursor cursor-b"'), PORTRAIT_ROWS)
        self.assertEqual(source.count('class="row-cursor cursor-c"'), PORTRAIT_ROWS)
        # All six tiers and all three passes are used.
        for tier in range(6):
            self.assertIn(f'class="t{tier} ', source)
        for pass_class in ("pa", "pb", "pc"):
            self.assertIn(f" {pass_class}\"", source)
        self.assertIn("calc(var(--pass) + var(--row))", source)
        self.assertIn("prefers-reduced-motion:reduce", source)
        self.assertNotIn("infinite", source)
        # Subject density: a readable portrait, neither a blob nor a sketch.
        glyphs = "".join(rows)
        visible = sum(1 for ch in glyphs if ch != " ")
        density = visible / (PORTRAIT_ROWS * PORTRAIT_COLS)
        self.assertGreater(density, 0.30)
        self.assertLess(density, 0.60)
        # Edge-aware glyphs trace contours.
        self.assertGreater(sum(glyphs.count(ch) for ch in "|/\\"), 150)

    @unittest.skipUnless(make_ascii_svg, "portrait renderer needs Pillow and NumPy")
    def test_portrait_renderer_rejects_wrong_grid(self) -> None:
        self.assertEqual((make_ascii_svg.COLS, make_ascii_svg.ROWS), (PORTRAIT_COLS, PORTRAIT_ROWS))
        with self.assertRaises(ValueError):
            make_ascii_svg.render_svg([[make_ascii_svg.Cell(" ", -1, False)] * 3])

    @unittest.skipUnless(make_ascii_svg, "portrait renderer needs Pillow and NumPy")
    def test_edge_glyph_orientation(self) -> None:
        self.assertEqual(make_ascii_svg._edge_glyph(1.0, 0.0), "|")
        self.assertEqual(make_ascii_svg._edge_glyph(0.0, 1.0), "-")
        self.assertEqual(make_ascii_svg._edge_glyph(1.0, 1.0), "/")
        self.assertEqual(make_ascii_svg._edge_glyph(1.0, -1.0), "\\")

    def test_info_card_and_heatmap_keep_one_shot_motion_contracts(self) -> None:
        card = (ASSETS / "info-card.svg").read_text(encoding="utf-8")
        heatmap = (REPOSITORY_ROOT / "contrib-heatmap.svg").read_text(encoding="utf-8")
        self.assertEqual(card.count('class="card-row"'), 13)
        self.assertIn("animation:card-row-in .40s", card)
        self.assertNotIn("infinite", card)
        self.assertIn("animation: cell-in .55s", heatmap)
        self.assertIn("cell-flash .70s", heatmap)
        self.assertNotIn("infinite", heatmap)


class CentrepieceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = make_connectome_svg.load_profile(REPOSITORY_ROOT / "data" / "profile.json")

    def test_marks_are_self_contained_symbols(self) -> None:
        self.assertEqual(set(MARKS), {"cassandra", "superconducted", "ephesus", "flybatch", "omi", "spdr"})
        for name in MARKS:
            with self.subTest(mark=name):
                wrapped = symbol(name)
                self.assertTrue(wrapped.startswith(f'<symbol id="mark-{name}" viewBox="0 0 64 64">'))
                self.assertNotIn("http", wrapped)
                self.assertNotIn("<use", wrapped)
        with self.assertRaises(KeyError):
            symbol("nope")
        self.assertEqual(all_symbols(["omi", "omi"]).count("<symbol"), 1)

    def test_connectome_fires_once_and_lights_every_node(self) -> None:
        source = (ASSETS / "connectome.svg").read_text(encoding="utf-8")
        self.assertEqual(source.count('<g class="node node-'), 6)
        self.assertEqual(source.count("<animateMotion"), 6)
        self.assertEqual(source.count("<mpath href=\"#axon-"), 6)
        self.assertEqual(source.count('<use href="#mark-'), 6)
        self.assertIn("SPIKE ARMED", source)
        self.assertIn("FIRED · 6/6 LIT", source)
        self.assertIn("prefers-reduced-motion:reduce", source)
        self.assertNotIn("infinite", source)
        arrivals = [float(value) for value in re.findall(r"--arrive:([0-9.]+)s", source)]
        self.assertEqual(len(arrivals), 6)
        self.assertTrue(all(t > make_connectome_svg.FIRE_AT for t in arrivals))
        for project in self.profile["flagships"][:6]:
            self.assertIn(project["name"], source)
            self.assertIn(project["note"], source)
        self.assertEqual(
            make_connectome_svg.render_svg(self.profile), make_connectome_svg.render_svg(self.profile)
        )

    def test_connectome_rejects_incomplete_profiles(self) -> None:
        profile = json.loads(json.dumps(self.profile))
        profile["flagships"] = profile["flagships"][:5]
        path = REPOSITORY_ROOT / "tests" / "_tmp_profile.json"
        try:
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaises(ValueError):
                make_connectome_svg.load_profile(path)
            profile["flagships"] = self.profile["flagships"][:6]
            profile["flagships"][0] = dict(profile["flagships"][0], state="bogus")
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaises(ValueError):
                make_connectome_svg.load_profile(path)
        finally:
            path.unlink(missing_ok=True)

    def test_ipl_prints_every_subsystem_with_an_honest_tally(self) -> None:
        source = (ASSETS / "ipl-map.svg").read_text(encoding="utf-8")
        self.assertEqual(source.count("<clipPath id=\"ipl-line-"), 9)
        self.assertEqual(source.count('class="lamp"'), 6)
        self.assertEqual(source.count('<use href="#mark-'), 6)
        self.assertIn("IPL COMPLETE · RC=0000", source)
        self.assertIn("MESSAGE IDS ARE NOT IBM", source)
        self.assertIn("prefers-reduced-motion:reduce", source)
        self.assertNotIn("infinite", source)
        states = [p["state"] for p in self.profile["flagships"][:6]]
        for state, label in make_ipl_svg.STATE_LABEL.items():
            if state in states:
                self.assertIn(f"{states.count(state)} {label}", source)
        fixed = date(2026, 10, 25)
        self.assertEqual(
            make_ipl_svg.render_svg(self.profile, today=fixed),
            make_ipl_svg.render_svg(self.profile, today=fixed),
        )
        self.assertIn("2026-10-25", make_ipl_svg.render_svg(self.profile, today=fixed))

    def test_static_renders_carry_no_motion_classes_that_hide_content(self) -> None:
        static = make_connectome_svg.render_svg(self.profile, static=True)
        self.assertIn('class="connectome static"', static)
        static_ipl = make_ipl_svg.render_svg(self.profile, static=True, today=date(2026, 10, 25))
        self.assertIn('class="ipl static"', static_ipl)


if __name__ == "__main__":
    unittest.main()
