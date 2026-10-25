#!/usr/bin/env python3
"""Brand marks for the six flagship projects, as inline SVG symbols.

Every mark is a 64 by 64 drawing.  ``symbol(name)`` wraps one as a
``<symbol id="mark-<name>" viewBox="0 0 64 64">`` so a renderer can inline it
once in ``<defs>`` and place it with ``<use href="#mark-<name>">``.  Inlining
is required: GitHub serves README images through a proxy and an SVG inside an
``<img>`` cannot load external resources.

Sources and licences
--------------------
- ``cassandra``: the Forecast mark, small on-dark variant, from
  Cassandra-Collective/.github ``brand/svg/cassandra-mark-small-on-dark.svg``
  (CC BY-ND 4.0, Mert Efe Şensoy).
- ``superconducted``: the small on-dark mark from SuperconducTED/.github
  ``brand/kit/svg/superconducted-mark-small-on-dark.svg``.
- ``ephesus``: ``docs/brand/ephesus-64.svg`` from the Ephesus repository (MIT).
- ``flybatch``: ``site/favicon.svg`` from the FlyBatch repository (MIT), with
  the card ``<use>`` expanded so the symbol needs no nested defs.
- ``omi`` and ``spdr``: drawn here for the profile (a DDR4 module and a chip
  with eight copper-trace legs, after spdr's banner).

No element in this module may reference an external resource.
"""

from __future__ import annotations


MARKS: dict[str, str] = {
    "cassandra": (
        '<path d="M51.701 57.216 C38.57 67.476 19.764 65.94 8.47 53.687 C-2.823 41.435 -2.823 22.565 '
        "8.47 10.313 C19.764 -1.94 38.57 -3.476 51.701 6.784 L43.821 16.87 C35.942 10.715 24.658 11.636 "
        "17.882 18.988 C11.106 26.339 11.106 37.661 17.882 45.012 C24.658 52.364 35.942 53.285 43.821 "
        '47.13 Z" fill="#f4efe6"/>'
        '<path d="M61.072 23.112 C62.843 28.905 62.843 35.095 61.072 40.888 L51.891 38.081 C53.103 34.118 '
        '53.103 29.882 51.891 25.919 Z" fill="#d2a65a"/>'
    ),
    "superconducted": (
        '<circle cx="32" cy="32" r="28" fill="none" stroke="#eef3f5" stroke-width="6"/>'
        '<path d="M30 6 L34 6 L34 16 L30 16 Z M34 26 L46 26 L46 38 L34 38 Z" fill="#eef3f5"/>'
        '<path d="M12 20 L22 20 L22 24 L16 24 L16 40 L22 40 L22 44 L12 44 Z M52 44 L42 44 L42 40 L48 40 '
        'L48 24 L42 24 L42 20 L52 20 Z" fill="#4fd6e6"/>'
    ),
    "ephesus": (
        '<rect x="0" y="0" width="64" height="64" fill="#221A14"/>'
        '<rect x="2" y="2" width="60" height="60" fill="#F4EDE0"/>'
        '<rect x="14" y="8" width="36" height="2" fill="#E8A987"/>'
        '<rect x="14" y="10" width="36" height="2" fill="#C4552D"/>'
        '<rect x="14" y="12" width="36" height="1" fill="#4A3B2C"/>'
        '<rect x="16" y="13" width="32" height="6" fill="#C4552D"/>'
        '<rect x="19" y="14" width="6" height="4" fill="#4A3B2C"/>'
        '<rect x="20" y="15" width="4" height="2" fill="#E8A987"/>'
        '<rect x="21" y="15" width="2" height="2" fill="#4A3B2C"/>'
        '<rect x="39" y="14" width="6" height="4" fill="#4A3B2C"/>'
        '<rect x="40" y="15" width="4" height="2" fill="#E8A987"/>'
        '<rect x="41" y="15" width="2" height="2" fill="#4A3B2C"/>'
        '<rect x="18" y="19" width="28" height="2" fill="#4A3B2C"/>'
        '<rect x="22" y="21" width="1" height="29" fill="#221A14"/>'
        '<rect x="42" y="21" width="1" height="29" fill="#221A14"/>'
        '<rect x="23" y="21" width="4" height="29" fill="#E7DCC6"/>'
        '<rect x="27" y="21" width="1" height="29" fill="#4A3B2C"/>'
        '<rect x="28" y="21" width="4" height="29" fill="#E7DCC6"/>'
        '<rect x="32" y="21" width="1" height="29" fill="#4A3B2C"/>'
        '<rect x="33" y="21" width="4" height="29" fill="#D3C4A5"/>'
        '<rect x="37" y="21" width="1" height="29" fill="#4A3B2C"/>'
        '<rect x="38" y="21" width="4" height="29" fill="#4A3B2C"/>'
        '<rect x="18" y="50" width="28" height="1" fill="#E7DCC6"/>'
        '<rect x="18" y="51" width="28" height="1" fill="#D3C4A5"/>'
        '<rect x="18" y="52" width="28" height="1" fill="#D3C4A5"/>'
        '<rect x="20" y="53" width="24" height="2" fill="#4A3B2C"/>'
        '<rect x="16" y="55" width="32" height="2" fill="#D3C4A5"/>'
        '<rect x="16" y="57" width="32" height="1" fill="#4A3B2C"/>'
        '<rect x="14" y="58" width="36" height="2" fill="#4A3B2C"/>'
    ),
    "flybatch": (
        '<g stroke-width="1.6" stroke-linejoin="round">'
        '<path d="M18 6 H62 V42 H12 V12 Z" fill="#e2d3a6" stroke="#9a8445"/>'
        '<path d="M14 11 H58 V47 H8 V17 Z" fill="#ebdcb3" stroke="#a08a4a"/>'
        '<path d="M9 17 H53 V53 H3 V23 Z" fill="#f3e7c4" stroke="#a8914f"/>'
        "</g>"
        '<g fill="#3b3f4a">'
        '<rect x="7" y="27" width="2.4" height="4.4" rx="0.4"/>'
        '<rect x="7" y="37" width="2.4" height="4.4" rx="0.4"/>'
        '<rect x="12" y="45" width="2.4" height="4.4" rx="0.4"/>'
        '<rect x="44" y="21" width="2.4" height="4.4" rx="0.4"/>'
        '<rect x="47" y="31" width="2.4" height="4.4" rx="0.4"/>'
        '<rect x="47" y="44" width="2.4" height="4.4" rx="0.4"/>'
        "</g>"
        '<g transform="translate(28 36) rotate(-18) scale(0.98)">'
        '<ellipse cx="-7" cy="3" rx="5.5" ry="11" transform="rotate(24 -7 3)" fill="#e6edf8" '
        'fill-opacity="0.92" stroke="#8a96ad" stroke-width="1"/>'
        '<ellipse cx="7" cy="3" rx="5.5" ry="11" transform="rotate(-24 7 3)" fill="#e6edf8" '
        'fill-opacity="0.92" stroke="#8a96ad" stroke-width="1"/>'
        '<ellipse cx="0" cy="7" rx="4.6" ry="7.5" fill="#c08a3e"/>'
        '<path d="M-4.2 6 H4.2 M-4.4 9.5 H4.4" stroke="#6b4a1c" stroke-width="1.3"/>'
        '<ellipse cx="0" cy="-3.5" rx="5" ry="4.6" fill="#9a6b2c"/>'
        '<circle cx="0" cy="-9.5" r="3.6" fill="#9a6b2c"/>'
        '<circle cx="-3" cy="-10.2" r="2.5" fill="#e0262b"/>'
        '<circle cx="3" cy="-10.2" r="2.5" fill="#e0262b"/>'
        "</g>"
    ),
    "omi": (
        '<rect x="4" y="19" width="56" height="24" rx="1.5" fill="#0f2a22" stroke="#2fd99a" stroke-width="2"/>'
        '<g fill="#1c4a3c" stroke="#2fd99a" stroke-width="1">'
        '<rect x="8" y="23" width="7" height="9"/><rect x="17" y="23" width="7" height="9"/>'
        '<rect x="26" y="23" width="7" height="9"/><rect x="37" y="23" width="7" height="9"/>'
        '<rect x="46" y="23" width="7" height="9"/>'
        "</g>"
        '<rect x="34" y="23" width="2" height="9" fill="#2fd99a" fill-opacity=".5"/>'
        '<g fill="#dca152">'
        '<rect x="7" y="44" width="2.4" height="6"/><rect x="11" y="44" width="2.4" height="6"/>'
        '<rect x="15" y="44" width="2.4" height="6"/><rect x="19" y="44" width="2.4" height="6"/>'
        '<rect x="23" y="44" width="2.4" height="6"/><rect x="27" y="44" width="2.4" height="6"/>'
        '<rect x="31" y="44" width="2.4" height="6"/>'
        '<rect x="39" y="44" width="2.4" height="6"/><rect x="43" y="44" width="2.4" height="6"/>'
        '<rect x="47" y="44" width="2.4" height="6"/><rect x="51" y="44" width="2.4" height="6"/>'
        '<rect x="55" y="44" width="2.4" height="6"/>'
        "</g>"
        '<rect x="34.5" y="43" width="3" height="8" fill="#07090e"/>'
    ),
    "spdr": (
        '<g fill="none" stroke="#dca152" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M22 25 L13 17 L5 21"/><path d="M22 30 L12 28 L4 32"/>'
        '<path d="M22 34 L12 36 L4 40"/><path d="M22 39 L13 47 L5 51"/>'
        '<path d="M42 25 L51 17 L59 21"/><path d="M42 30 L52 28 L60 32"/>'
        '<path d="M42 34 L52 36 L60 40"/><path d="M42 39 L51 47 L59 51"/>'
        "</g>"
        '<g fill="#f3d49b">'
        '<circle cx="5" cy="21" r="2"/><circle cx="4" cy="32" r="2"/><circle cx="4" cy="40" r="2"/>'
        '<circle cx="5" cy="51" r="2"/><circle cx="59" cy="21" r="2"/><circle cx="60" cy="32" r="2"/>'
        '<circle cx="60" cy="40" r="2"/><circle cx="59" cy="51" r="2"/>'
        "</g>"
        '<rect x="22" y="22" width="20" height="20" rx="1.5" fill="#141a16" stroke="#dca152" stroke-width="2"/>'
        '<rect x="27" y="27" width="10" height="10" fill="none" stroke="#dca152" stroke-width="1" stroke-opacity=".7"/>'
        '<circle cx="25" cy="25" r="1.5" fill="#f3d49b"/>'
    ),
}


def symbol(name: str) -> str:
    """Return the named mark wrapped as a reusable ``<symbol>``."""

    try:
        body = MARKS[name]
    except KeyError as exc:
        raise KeyError(f"unknown mark {name!r}; known: {', '.join(sorted(MARKS))}") from exc
    return f'<symbol id="mark-{name}" viewBox="0 0 64 64">{body}</symbol>'


def all_symbols(names: list[str] | tuple[str, ...] | None = None) -> str:
    chosen = list(MARKS) if names is None else list(dict.fromkeys(names))
    return "".join(symbol(name) for name in chosen)
