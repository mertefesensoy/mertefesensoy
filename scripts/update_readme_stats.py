#!/usr/bin/env python3
"""Refresh the human-readable contribution summary in the profile README."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPOSITORY_ROOT / "data" / "contributions.json"
DEFAULT_README = REPOSITORY_ROOT / "README.md"

START_MARKER = "<!-- PROFILE_STATS:START -->"
END_MARKER = "<!-- PROFILE_STATS:END -->"


class StatsUpdateError(RuntimeError):
    """Raised when contribution data or the README marker block is invalid."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StatsUpdateError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> object:
    raise StatsUpdateError(f"non-finite JSON number {value!r} is not allowed")


def load_contribution_summary(path: Path) -> Mapping[str, object]:
    """Load the subset of the contribution contract needed by the README."""

    try:
        payload = json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except StatsUpdateError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatsUpdateError(f"unable to read contribution data from {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise StatsUpdateError("contribution data must be a JSON object")
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str):
        raise StatsUpdateError("generated_at must be an ISO-8601 timestamp")
    try:
        parsed_generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StatsUpdateError("generated_at must be an ISO-8601 timestamp") from exc
    if parsed_generated_at.tzinfo is None:
        raise StatsUpdateError("generated_at must include a timezone")

    stats = payload.get("stats")
    if not isinstance(stats, dict):
        raise StatsUpdateError("stats must be a JSON object")
    for field in ("yearly_total", "current_streak", "longest_streak"):
        value = stats.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise StatsUpdateError(f"stats.{field} must be a non-negative integer")

    best_day = stats.get("best_day")
    if best_day is not None:
        if not isinstance(best_day, dict):
            raise StatsUpdateError("stats.best_day must be an object or null")
        raw_date = best_day.get("date")
        try:
            parsed_best_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else None
        except ValueError as exc:
            raise StatsUpdateError("stats.best_day.date must be an ISO date") from exc
        if parsed_best_date is None or parsed_best_date.isoformat() != raw_date:
            raise StatsUpdateError("stats.best_day.date must be an ISO date")
        count = best_day.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise StatsUpdateError("stats.best_day.count must be a positive integer")

    return {
        "generated_date": parsed_generated_at.date(),
        "yearly_total": stats["yearly_total"],
        "current_streak": stats["current_streak"],
        "longest_streak": stats["longest_streak"],
        "best_day": best_day,
    }


def _plural(value: int, singular: str, plural: str | None = None) -> str:
    return singular if value == 1 else (plural or f"{singular}s")


def build_summary(values: Mapping[str, object]) -> str:
    """Build one accessible line of prose from validated summary values."""

    total = int(values["yearly_total"])
    current = int(values["current_streak"])
    longest = int(values["longest_streak"])
    generated_date = values["generated_date"]
    if not isinstance(generated_date, date):
        raise StatsUpdateError("generated_date must be a date")

    best_day = values.get("best_day")
    if best_day is None:
        best_label = "no contributions yet"
    else:
        if not isinstance(best_day, Mapping):
            raise StatsUpdateError("best_day must be a mapping or null")
        best_count = int(best_day["count"])
        best_label = (
            f"{best_count:,} {_plural(best_count, 'contribution')} "
            f"on {best_day['date']}"
        )

    return (
        '<p align="center"><sub><strong>GITHUB.ACTIVITY / LAST 12 MONTHS</strong> · '
        f"Total: {total:,} {_plural(total, 'contribution')} · Current streak: {current:,} "
        f"{_plural(current, 'day')} · Longest streak: {longest:,} "
        f"{_plural(longest, 'day')} · Best day: {best_label} · "
        f"Generated: {generated_date.isoformat()}</sub></p>"
    )


def replace_stats_block(readme: str, summary: str) -> str:
    """Replace only the content enclosed by the unique profile-stat markers."""

    if "\n" in summary or "\r" in summary:
        raise StatsUpdateError("the profile summary must be exactly one line")
    start_count = readme.count(START_MARKER)
    end_count = readme.count(END_MARKER)
    if start_count != 1 or end_count != 1:
        raise StatsUpdateError(
            "README must contain exactly one PROFILE_STATS:START marker and "
            "exactly one PROFILE_STATS:END marker"
        )

    start = readme.index(START_MARKER) + len(START_MARKER)
    end = readme.index(END_MARKER)
    if start > end:
        raise StatsUpdateError("PROFILE_STATS:START must precede PROFILE_STATS:END")

    newline = "\r\n" if "\r\n" in readme else "\n"
    return readme[:start] + newline + summary + newline + readme[end:]


def _write_text_atomic(path: Path, text: str) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary_name = temporary.name
        try:
            os.chmod(temporary_name, path.stat().st_mode)
        except OSError:
            pass
        os.replace(temporary_name, path)
    except OSError as exc:
        raise StatsUpdateError(f"unable to update {path}: {exc}") from exc
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def update_readme(data_path: Path, readme_path: Path) -> bool:
    """Refresh the marker block and return whether the README changed."""

    values = load_contribution_summary(data_path)
    summary = build_summary(values)
    try:
        original = readme_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise StatsUpdateError(f"unable to read {readme_path}: {exc}") from exc
    updated = replace_stats_block(original, summary)
    if updated == original:
        return False
    _write_text_atomic(readme_path, updated)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    args = parser.parse_args(argv)

    try:
        changed = update_readme(args.data, args.readme)
    except StatsUpdateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{'Updated' if changed else 'Already current'}: {args.readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
