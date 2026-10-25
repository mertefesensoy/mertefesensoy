# Profile README redesign: portrait v2, two centrepieces, upstream ledger

**Date:** 2026-10-25
**Status:** shipped on branch `claude/github-readme-redesign-7ba903`; the owner chose the IPL boot map as the README centrepiece (2026-10-25)
**Plan:** [2026-10-25-profile-redesign-plan.md](./2026-10-25-profile-redesign-plan.md)

## 1. Problem / Motivation

The profile README predated FlyBatch, the SuperconducTED and Cassandra Collective brand
kits, spdr on crates.io, Ephesus and the upstream pull-request work. Its portrait was flat:
one fill colour, density-only glyphs, rendered from a 239 px prepped image. The owner asked
for a centrepiece nobody had seen on a GitHub profile, a rebuilt portrait with real tonal
levels, and the open-source effort made visible, all on the existing honest, self-contained,
token-free pipeline.

## 2. What Changed

| File | Change |
|---|---|
| `assets/profile-source.jpg` | New 1400 px square crop of the original 2821 by 3762 photograph; replaces the 460 px PNG. |
| `assets/profile-prepped.png` | Regenerated at 900 px: GrabCut cut-out, largest-component filter, CLAHE and percentile stretch, white field. |
| `assets/mert-ascii.svg` | Portrait v2: 150 by 80 cells, six tiers, edge glyphs, three-pass reveal (101 KB). |
| `assets/connectome.svg` | New centrepiece A: soma, LIF trace, six axons, one spike, six lit nodes with brand marks. |
| `assets/ipl-map.svg` | New centrepiece B: stylised IPL console loading six subsystems with status lamps and an honest tally. |
| `assets/pr-ledger.svg` | New daily asset: merged, open and repository counts, latest merged PRs, per-repository bars. |
| `assets/info-card.svg` | Re-rendered from the new profile data (active channels: FlyBatch, SuperconducTED, Cassandra). |
| `data/profile.json` | Six flagships with `state`, `url`, `mark`, `accent`, `asid`, `tagline`, `note`; refreshed roles and stack. |
| `data/upstream_prs.json` | New daily data: the upstream ledger (7 merged, 8 open, 9 repositories at first fetch). |
| `scripts/prep_photo.py` | Rewritten: seeds for the new framing, definite-background bands, connected-component filter, coverage guard, tone map. |
| `scripts/make_ascii_svg.py` | Rewritten: subject window, tiering, Sobel edge glyphs, tspan runs, three-pass CSS schedule. |
| `scripts/marks.py` | New: the six brand marks as inlinable `<symbol>` strings, with sources and licences. |
| `scripts/make_connectome_svg.py` | New: centrepiece A generator (stdlib). |
| `scripts/make_ipl_svg.py` | New: centrepiece B generator (stdlib), `--date` for reproducible output. |
| `scripts/fetch_upstream_prs.py` | New: GitHub search fetch, owner filter, deduplication, atomic JSON write (stdlib). |
| `scripts/render_ledger_svg.py` | New: ledger renderer (stdlib). |
| `scripts/validate_profile.py` | Validates the three new SVGs at 860 px, the ledger JSON (tally consistency, excluded owners), the richer flagship schema; the protocol-relative URL check now needs a dotted host so ASCII `//` runs pass. |
| `tests/test_profile_artwork.py` | Rewritten for v2 contracts: grid, tiers, passes, cursors, density, edge glyphs, marks, connectome, IPL, determinism. |
| `tests/test_profile_maintenance.py` | Identity fixture updated to the new flagship schema. |
| `tests/test_upstream_ledger.py`, `tests/fixtures/search_prs_fragment.json` | New: normalisation, counting, validation, rendering, rejection cases. |
| `.github/workflows/update-profile-art.yml` | Fetches and renders the ledger, re-renders both centrepieces daily, adds the new paths to `git add`. |
| `preview/compare.html` | Comparison page: both centrepieces inside a mock README frame, light/dark, replay, static toggle. |
| `README.md` | New composition; IPL boot map shown, connectome a three-edit swap away (heading, image, alt); six-flagship dossier; honest copy without em dashes. |
| `.gitignore` | Ignores `*.static.svg` preview companions. |
| `docs/implementations/_TEMPLATE.md`, `memory/MEMORY.md` | Created per the engineering standards. |

## 3. Implementation Approach

### Portrait v2 (`make_ascii_svg.py`)

`portrait_to_cells(path) -> list[list[Cell]]` is pure: it reads the prepped grayscale, crops
to the subject (square, bottom-anchored, 6% margin), resizes to 150 by 80, and classifies each
cell. `render_svg(cells, static=False) -> str` is pure and raises on a wrong grid. Each row is
one `<text>` with `xml:space="preserve"` and `textLength` pinned to 800 px; consecutive cells of
the same tier merge into one `<tspan class="tN pX">`. The row carries `--row`, the pass class
carries `--pass`, and the CSS delay is `calc(var(--pass) + var(--row))`, so the three passes
(shadows, mids, lights) each print top to bottom at 25 ms per row with a 2.2 s gap. Three
cursor rectangles per row sweep with each pass. Under `prefers-reduced-motion: reduce` every
tspan is visible and nothing moves; `--static` renders the same.

### Photo prep (`prep_photo.py`)

`prepare_portrait(source) -> Image` resizes to 900 px, runs GrabCut from fraction-based seeds
(face, hair, suit definite; head and shoulders probable; top band and side bands definite
background), keeps the largest connected component (the wallpaper medallions otherwise survive
as islands), closes small holes, and raises if coverage leaves 18 to 70% of the frame. The tone
map is CLAHE, a mild unsharp mask, and a 1st to 99th percentile stretch scaled to 0.93 so the
brightest subject tone never becomes background.

### Centrepieces

Both read `data/profile.json`, inline the marks from `marks.py` as symbols, and are
deterministic for a fixed date. The connectome computes each axon's length by sampling the
cubic and sets `--arrive = FIRE_AT + length / 420 px/s`; the spike dots use SMIL
`animateMotion` over `mpath`, hidden by CSS under reduced motion. The IPL console reuses the
portrait's clip-path wipe per line; lamps and their rings animate after each wipe.

### Ledger

`search_pull_requests` pages `GET /search/issues` with `advanced_search=true`;
`normalize` drops PRs whose repository owner is in `EXCLUDED_OWNERS` and deduplicates by
`repo#number`; `build_payload` counts, tallies per repository and keeps the latest merged and
open records. The JSON records its caveats. `render_ledger_svg.py` draws tiles, the latest
merged list and per-repository bars (merged solid, open hollow).

## 4. Mathematical / Statistical Details

- **Tiering.** `d = 1 - L^0.92`; `d' = clip((d - p2) / (p98 - p2), 0, 1)` over non-background
  cells; `tier = floor(6 d')` clamped to 5; glyph index `floor(3 frac(6 d'))`.
- **Edges.** `np.gradient` on an isotropic 150 by 149 copy, pooled to cell rows;
  `m = hypot(gx, gy)`; threshold at the 85th percentile of `m` over subject cells; glyph from
  the gradient angle modulo 180: within 22.5 degrees of 0 gives `|`, of 90 gives `-`, otherwise
  `/` when `gx * gy > 0` else `\`.
- **Membrane trace.** `level(s) = min(1, 1 - e^{-3.2 s} + 0.045 sin(31 s)(1 - s) + 0.08 s)`
  for `s` in [0, 1], drawn to 98.5% of the rest-to-threshold span, then the spike.
- **Ledger bars.** Width proportional to count over the largest merged-plus-open total among
  the six shown repositories, minimum 1 px for a non-zero count.

## 5. Design Decisions

- **Both centrepieces built**, compared on `preview/compare.html`; the owner chose the IPL boot
  map for the README, and the connectome stays a three-edit swap away (`CENTREPIECE` markers).
- **Positive tone mapping** (brighter photo tone, brighter ink and denser glyph) replaced the
  old paper mapping that rendered the face as a negative.
- **Blue shadows to ivory light** per the owner; the mid tier was neutralised slightly
  (`#bcbdcf`) so skin does not read grey-blue.
- **Marks inlined**, never fetched; ids namespaced `mark-*` and FlyBatch's `<use>` expanded.
- **Daily re-render of the centrepieces** so the IPL date stays current; both are stdlib.
- **Owner filter** mirrors the OSS HQ tracker; the first fetch matched it exactly.
- **Honesty register** throughout: FlyBatch has not run on IBM Z; Chorus Stage 0 is a negative
  result; Ephesus is pre-alpha; message ids are marked as not IBM's.

## 6. Verification

Run from the repository root (Python 3.13 with Pillow, NumPy and OpenCV for the portrait):

```bash
python scripts/prep_photo.py && python scripts/make_ascii_svg.py
python scripts/make_info_card.py
python scripts/make_connectome_svg.py && python scripts/make_ipl_svg.py --date 2026-10-25
python scripts/fetch_upstream_prs.py && python scripts/render_ledger_svg.py
python -m unittest discover -s tests -v      # 42 tests
python scripts/validate_profile.py           # "Profile validation passed."
git diff --check
python -m http.server 8765                   # http://127.0.0.1:8765/preview/compare.html
```

Done on 2026-10-25: 42 tests pass on Python 3.13; the same suite passes on a stdlib-only
Python 3.12 virtual environment (the workflow's interpreter) with the two Pillow-dependent
portrait tests skipped, and every daily step (validator, both centrepieces, ledger render,
ledger fetch from the fixture, README stats) runs there; the portrait, both centrepieces and
the ledger were viewed in the built-in browser at natural size and on the comparison page in
dark and light; the first live fetch returned 7 merged and 8 open upstream PRs across 9
repositories, matching the OSS HQ tracker. Not yet verified: rendering on github.com (the
profile page renders `main` only) and a real Actions run of the extended workflow.

The stdlib-only check, from a short path (VectorCraft and other tools misbehave past 260
characters):

```bash
py -3.12 -m venv C:/tpf/v312 --without-pip
C:/tpf/v312/Scripts/python.exe -m unittest discover -s tests
C:/tpf/v312/Scripts/python.exe scripts/validate_profile.py
```

## 7. Related Docs

- Plan: [2026-10-25-profile-redesign-plan.md](./2026-10-25-profile-redesign-plan.md)
- Brand sources: Cassandra-Collective/.github `brand/`, SuperconducTED/.github `brand/`,
  Ephesus `docs/brand/`, FlyBatch `site/favicon.svg`
- Workflow: `.github/workflows/update-profile-art.yml`
