# Profile README redesign: plan

**Date:** 2026-10-25
**Status:** built; see [2026-10-25-profile-redesign.md](./2026-10-25-profile-redesign.md) for what shipped and how it was verified. Deviations from this plan: both centrepieces are re-rendered daily by the workflow (stdlib only) so the IPL date stays current; the connectome cards carry no stack label (the note needed the room); `assets/connectome.svg` is 500 px tall rather than 440.

## 1. Problem / Motivation

The profile README dates from the first ASCII-portrait composition. Since then the public
work has changed shape: FlyBatch shipped with golden fingerprints from x86-64 to emulated
MVS 3.8j, SuperconducTED and the Cassandra Collective became organisations with their own
VectorCraft brand kits, spdr reached v0.1.0 on crates.io, Ephesus is built in public, and
there is a steady stream of upstream pull requests (zowe, microsoft/vcpkg, mitiq,
worldmonitor). None of that is on the profile. The portrait itself is flat: one fill
colour, density-only glyphs, rendered from a 239 px prepped image, so it reads as a
halftone with no tonal depth.

The brief: a centrepiece nobody has seen on a GitHub profile, built on the same honest,
self-contained, no-token, reduced-motion-safe pipeline the repository already has.

## 2. Decisions taken with the owner (2026-10-25)

| Question | Decision |
|---|---|
| Centrepiece | Build **both** prototypes, the spiking connectome and the IPL boot map, and compare on a side-by-side preview page before choosing. |
| Visual system | IBM Carbon console shell; each flagship node carries its **own** brand mark and accent (CASSANDRA bronze and night, SuperconducTED cryostat, Ephesus column, FlyBatch fly-on-cards, spdr copper, OMI). |
| Portrait | Keep it as the opening beat and the trigger of the centrepiece, but rebuild the inner system: **tonal tiers, layered print reveal, edge-aware glyphs, and a photo re-prep** from the 2821 by 3762 original. |
| Portrait tone | **Blue shadows, ivory light.** |
| Nodes | **Six flagships:** FlyBatch, SuperconducTED, Cassandra Collective (CASSANDRA, Chorus, Dervish as one node), Ephesus, OMI, spdr. |
| Live data | Add a daily **upstream PR ledger** next to the contribution heatmap. |
| Comparison | **Side-by-side preview page** in a mock GitHub README frame, light and dark. |

## 3. Architecture

Two classes of asset, as today:

- **Built locally, committed as output.** The portrait (needs Pillow and OpenCV), the
  connectome and IPL SVGs (stdlib only, from `data/profile.json`), the info card. They are
  regenerated only when their inputs change.
- **Rendered daily by GitHub Actions, stdlib only.** The contribution heatmap and, new, the
  upstream PR ledger. The workflow's `git add` list and the `PROFILE_STATS` markers are a
  contract; the ledger adds `data/upstream_prs.json` and `assets/pr-ledger.svg` to it.

Constraints every SVG must satisfy (enforced by `scripts/validate_profile.py`):
self-contained (no external URL, no `@import`, no `url()` outside `#`), no `<script>` or
`<foreignObject>`, `role="img"` with one `<title>` and one `<desc>` referenced by
`aria-labelledby`, a fixed pixel width, motion that plays once and is disabled under
`prefers-reduced-motion: reduce`. Fonts are a system monospace stack; brand marks are
inlined as `<symbol>` elements and referenced with `href="#id"`.

## 4. What will change

| File | Change |
|---|---|
| `assets/profile-source.jpg` | New 1400 px square crop of the original photograph (replaces the 460 px PNG as the portrait source). |
| `scripts/prep_photo.py` | Re-prep: higher working resolution, cleaner GrabCut mask, local contrast tuned so ear, eye, nose, tie and lapel read; writes `profile-prepped.png` at 900 px. |
| `scripts/make_ascii_svg.py` | v2 renderer: 150 by 80 cell grid, six luminance tiers with their own fill and glyph ramp, Sobel edge glyphs, three-pass layered reveal, blue-to-ivory palette. |
| `scripts/make_connectome_svg.py` | New. Renders `assets/connectome.svg` from `profile.json`: a soma, six axons, six project nodes with inlined marks, a LIF membrane trace, one spike that propagates once. |
| `scripts/make_ipl_svg.py` | New. Renders `assets/ipl-map.svg`: an IPL console that brings the six subsystems up line by line with status lights. |
| `scripts/marks.py` | New. The six brand marks as `<symbol>` strings, ids namespaced to avoid collisions. |
| `scripts/fetch_upstream_prs.py` | New, stdlib only. GitHub search API for public PRs authored by the user outside their own owners; writes `data/upstream_prs.json`. Uses `GITHUB_TOKEN` when present (Actions provides one; no PAT). |
| `scripts/render_ledger_svg.py` | New. Renders `assets/pr-ledger.svg` (merged and open counts, per-repo bars, latest merged PRs). |
| `scripts/validate_profile.py` | Validates the three new SVGs and the ledger JSON; flagship schema gains `url`, `mark`, `accent`, `tagline`. |
| `data/profile.json` | Six flagships with marks, accents, honest status lines; refreshed stack and roles. |
| `tests/test_profile_artwork.py`, `tests/test_profile_maintenance.py`, new `tests/test_upstream_ledger.py` | Contracts for the v2 portrait (tiers, passes, edge glyphs), the two centrepieces, and the ledger parser/filter with a fixture. |
| `.github/workflows/update-profile-art.yml` | Two new steps (fetch ledger, render ledger) and two new paths in `git add`. |
| `preview/compare.html` | The comparison page: both centrepieces in a mock README frame, light and dark, served locally. |
| `README.md` | New composition: whoami, centrepiece, contributions, upstream ledger, links, dossier with six flagships and systems work. |
| `memory/MEMORY.md` | Project memory, created. |

## 5. Implementation approach

### 5.1 Portrait v2

`portrait_to_cells(path) -> list[list[Cell]]` where `Cell = (glyph, tier, is_edge)`.

1. Load the prepped grayscale, resize to `COLS x ROWS` (150 by 80) with Lanczos, light
   unsharp mask.
2. Luminance `L` in [0, 1] with gamma 0.9. Cells with `L >= 0.97` are background: a space.
3. **Tier** `t = min(5, floor((1 - L) * 6))` after a mild contrast stretch so the six bins
   are populated. Tier 0 is the brightest lit skin, tier 5 the deepest shadow.
4. **Glyph** within a tier comes from that tier's three-character ramp, indexed by the
   fractional part of `(1 - L) * 6`, so density still varies inside a tier.
5. **Edge glyphs.** Sobel gradients `gx, gy` on the resized image. Where the magnitude is
   above the 80th percentile of non-background cells, the glyph is replaced by the
   orientation glyph: `|` for near-vertical, `-` or `_` for near-horizontal, `/` and `\` for
   the diagonals. The cell keeps its tier colour.
6. Rendering: one `<text>` per row with `xml:space="preserve"` and `textLength` pinned to
   the art width; consecutive cells of the same tier are merged into one `<tspan class="tN">`.
7. **Layered reveal.** Three passes: shadows (tiers 5, 4), mids (3, 2), lights (1, 0).
   Each `tspan` gets a pass class; the row sets `--row`. Delay is
   `calc(var(--pass) + var(--row) * 25ms)`, so each pass prints top to bottom and the
   portrait develops shadows first, like a print. A sweep cursor accompanies each pass.
   Total run about 6.5 s. Under reduced motion every tspan is simply visible.

Palette (blue shadows to ivory light): tier 5 `#26478f`, 4 `#3a68c9`, 3 `#5f8fe8`,
2 `#a6b9dd`, 1 `#e3dccb`, 0 `#f8f1e0`.

### 5.2 Connectome

Layout 860 by 440. A soma at the left (concentric rings, label `mertefe`), six nodes in two
columns at the right, cubic axons from the soma to each node. Each node: a 28 px mark, the
name, a one-line tagline, an honest status pill. A membrane-potential trace along the
bottom rises, crosses a dashed threshold, and the spike fires: the axons "charge" with
`stroke-dashoffset`, a spike dot rides each axon with SMIL `animateMotion` over an `mpath`,
and each node lights at its arrival time (opacity and accent glow). Everything plays once.
The spike is scheduled after the portrait's run so the two images read as one sequence.

### 5.3 IPL boot map

Layout 860 by 400. A z/OS-style console: header line (`IPL SYS1.MERTEFE LOADPARM 0A80`),
then one line per subsystem, printed with the portrait's row wipe: mark, subsystem name,
address-space id, status light, one-line role. Lights switch on at the end of each line's
wipe. Final line `IPL COMPLETE RC=0000` with the honest tally (how many up, how many in
research, how many pre-alpha or negative). Message prefixes are stylised, not real IBM
message ids, and the desc says so.

### 5.4 Upstream PR ledger

`fetch_upstream_prs.py`: `GET /search/issues?q=is:pr+author:<user>+is:public&per_page=100`,
paged, with `GITHUB_TOKEN` as a bearer token when present. The repository owner of each PR
is compared against an `EXCLUDED_OWNERS` set (the user and their own organisations, the
same heuristic the OSS HQ tracker uses). Output: counts (merged, open, closed unmerged,
repositories), a per-repo merged tally, and the latest merged and open PRs (number, title,
repo, date). Failures leave the previous JSON untouched, as the contribution fetch does.

`render_ledger_svg.py`: 860 wide, counts as tiles, per-repo bars that grow once, the latest
six merged PRs as a listing. Titles are escaped and truncated.

### 5.5 Comparison page

`preview/compare.html` loads the two centrepiece SVGs beneath the portrait and info card
inside a mock GitHub README container, with a light/dark toggle and a replay button that
reloads the images. Served with `python -m http.server` so relative paths behave as on
GitHub.

## 6. Mathematical details

- **Luminance tiering.** With `L` the gamma-corrected luminance, `d = (1 - L)`,
  `t = min(5, floor(6 d'))` where `d' = clip((d - lo) / (hi - lo), 0, 1)` stretches the
  darkness range of non-background cells to the 2nd and 98th percentiles so that all six
  bins are used. Within-tier glyph index `g = floor(3 * frac(6 d'))`.
- **Edge detection.** Sobel kernels give `gx, gy`; magnitude `m = sqrt(gx^2 + gy^2)`;
  orientation `theta = atan2(gy, gx)`. The edge threshold is the 80th percentile of `m`
  over non-background cells. Orientation buckets (edge direction is perpendicular to the
  gradient): gradient angle within 22.5 degrees of vertical gives a horizontal edge glyph,
  within 22.5 degrees of horizontal gives `|`, otherwise a diagonal, with the sign of
  `gx * gy` choosing `/` or `\`.
- **Spike schedule.** Node `i` lights at `t_fire + L_i / v` where `L_i` is the axon path
  length and `v` a constant speed, so farther nodes light later, as a real propagation.
- **Contribution and ledger stats** are counts; the only derived figure is the per-repo bar
  width, proportional to merged count with a 1 px minimum.

## 7. Design decisions

- **Both centrepieces are built** because the owner wants to choose on sight, not on a
  sketch. The README ships with one; the other stays in `assets/` and the preview page.
- **Marks inlined as symbols, not fetched.** GitHub proxies README images through camo and
  an SVG cannot load external resources; inlining also keeps the validator's
  "self-contained" rule.
- **SMIL for the spike motion** rather than CSS `offset-path`: supported in `<img>` by
  every current engine, and the validator already permits it (it forbids only script,
  foreignObject, event handlers and external references).
- **No new daily commits for the centrepieces.** They depend on hand-curated status lines;
  regenerating them daily would only churn history.
- **Honesty register.** Status lines state the stage precisely: FlyBatch has not run on IBM Z
  hardware; Chorus Stage 0 closed as a negative result; Ephesus is pre-alpha; SuperconducTED
  is a research preview. House style: no em or en dashes in new copy; middle dots and colons.
- **Ledger owner filter** reuses the OSS HQ heuristic so the two counts agree.

## 8. Verification

```bash
python scripts/prep_photo.py && python scripts/make_ascii_svg.py
python scripts/make_connectome_svg.py && python scripts/make_ipl_svg.py
python scripts/fetch_upstream_prs.py && python scripts/render_ledger_svg.py
python -m unittest discover -s tests -v
python scripts/validate_profile.py
git diff --check
python -m http.server 8765   # then open http://127.0.0.1:8765/preview/compare.html
```

Visual checks in the built-in browser: each SVG at its natural size, the comparison page in
light and dark, reduced motion emulated, and the README on the branch in GitHub's file view.
The profile page itself only renders `main`, so the final check happens after merge.

## 9. Related docs

- `docs/implementations/2026-10-25-profile-redesign.md` (written after the build)
- Brand kits: `Cassandra-Collective/.github/brand`, `SuperconducTED/.github/brand`,
  `Ephesus/docs/brand`, `FlyBatch/site/favicon.svg`
