# Project memory: mertefesensoy profile README

Updated 2026-10-25.

## State

- Branch `claude/github-readme-redesign-7ba903` carries the 2026-10-25 redesign: portrait v2
  (tiers, edge glyphs, three-pass reveal), two centrepieces (IPL map shown in the README,
  connectome built and previewed), the daily upstream PR ledger, and the comparison page.
- **Decided 2026-10-25: the IPL boot map ships** in the README; the connectome stays built
  and previewable at `preview/compare.html` (serve the repository root with
  `python -m http.server 8765`). Swapping back means three edits in `README.md`: the `<h3>`
  (`./ipl.sh` to `./connectome.sh`), and the `<img>` src and alt inside the `CENTREPIECE` markers.
- GitHub renders the profile from `main` only; nothing is visible there until merged.

## How the pipeline splits

- Local, needs Pillow + NumPy + OpenCV: `prep_photo.py`, `make_ascii_svg.py`.
- Stdlib, run daily by Actions: contributions, upstream ledger, both centrepieces, README stats.
- The workflow's `git add` list and the `PROFILE_STATS` markers are a contract; add any new
  daily asset to both the workflow steps and that list.

## Rules that bit us

- SVGs must be self-contained: inline marks as `<symbol>`; `href` only to `#ids`.
- The validator's URL heuristic once tripped on ASCII `//` runs; it now needs a dotted host.
- Never put two `class` attributes on one element (the ledger did; XML rejects it).
- Fixture `profile_payload()` in the maintenance tests must track the flagship schema.
- House style in copy: no em or en dashes; middle dots and colons.

## Facts verified 2026-10-25

- spdr 0.1.1 on crates.io, repo `The-Open-Memory-Initiative-OMI/spdr`.
- FlyBatch latest release `v0.5.1-rc.1` (tester pre-release); has not run on IBM Z hardware.
- Upstream ledger first fetch: 7 merged, 8 open, 9 repositories (matches OSS HQ tracker).
