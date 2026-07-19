#!/usr/bin/env python3
"""Validate profile data, generated SVG assets, and local README images."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRIBUTIONS = REPOSITORY_ROOT / "data" / "contributions.json"
DEFAULT_PROFILE_DATA = REPOSITORY_ROOT / "data" / "profile.json"
DEFAULT_PORTRAIT_SVG = REPOSITORY_ROOT / "assets" / "mert-ascii.svg"
DEFAULT_INFO_CARD_SVG = REPOSITORY_ROOT / "assets" / "info-card.svg"
DEFAULT_HEATMAP_SVG = REPOSITORY_ROOT / "contrib-heatmap.svg"
DEFAULT_README = REPOSITORY_ROOT / "README.md"

EXPECTED_SVG_WIDTH = 860
MIN_CALENDAR_DAYS = 364
MAX_CALENDAR_DAYS = 371
USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
WIDTH_RE = re.compile(r"^860(?:\.0+)?(?:px)?$", re.IGNORECASE)
URL_FUNCTION_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
EXTERNAL_SCHEME_RE = re.compile(
    r"(?:https?|ftp|file|javascript|vbscript|data):", re.IGNORECASE
)
MARKDOWN_IMAGE_RE = re.compile(
    r"(?<!\\)!\[[^\]\r\n]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)]+))",
    re.MULTILINE,
)
REFERENCE_IMAGE_RE = re.compile(
    r"(?<!\\)!\[([^\]\r\n]*)\]\[([^\]\r\n]*)\]", re.MULTILINE
)
REFERENCE_DEFINITION_RE = re.compile(
    r"^[ \t]{0,3}\[([^\]\r\n]+)\]:[ \t]*(?:<([^>\r\n]+)>|([^\s]+))",
    re.MULTILINE,
)


class ProfileValidationError(RuntimeError):
    """Raised when any profile artifact violates its contract."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProfileValidationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> object:
    raise ProfileValidationError(f"non-finite JSON number {value!r} is not allowed")


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except ProfileValidationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileValidationError(f"unable to read JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProfileValidationError(f"{path} must contain a JSON object")
    return payload


def _nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProfileValidationError(f"{field} must be a non-negative integer")
    return value


def _positive_integer(value: object, field: str) -> int:
    result = _nonnegative_integer(value, field)
    if result == 0:
        raise ProfileValidationError(f"{field} must be a positive integer")
    return result


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _iso_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ProfileValidationError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ProfileValidationError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ProfileValidationError(f"{field} must use canonical YYYY-MM-DD form")
    return parsed


def _calculated_stats(days: Sequence[tuple[date, int]]) -> dict[str, object]:
    by_date = {day: count for day, count in days}
    first_day = min(by_date)
    last_day = max(by_date)
    monthly_totals: OrderedDict[str, int] = OrderedDict()
    longest_streak = 0
    running_streak = 0
    cursor = first_day
    while cursor <= last_day:
        count = by_date.get(cursor, 0)
        month = cursor.strftime("%Y-%m")
        monthly_totals.setdefault(month, 0)
        monthly_totals[month] += count
        if count > 0:
            running_streak += 1
            longest_streak = max(longest_streak, running_streak)
        else:
            running_streak = 0
        cursor += timedelta(days=1)

    streak_cursor = last_day - timedelta(days=1) if by_date[last_day] == 0 else last_day
    current_streak = 0
    while streak_cursor >= first_day and by_date.get(streak_cursor, 0) > 0:
        current_streak += 1
        streak_cursor -= timedelta(days=1)

    contributing_days = [(day, count) for day, count in days if count > 0]
    best = max(contributing_days, key=lambda item: (item[1], item[0])) if contributing_days else None
    return {
        "yearly_total": sum(count for _, count in days),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "best_day": {"date": best[0].isoformat(), "count": best[1]} if best else None,
        "monthly_totals": dict(monthly_totals),
    }


def validate_contribution_data(path: Path) -> Mapping[str, object]:
    """Validate the complete stable contribution JSON contract."""

    payload = _load_json_object(path)
    if payload.get("schema_version") != 1:
        raise ProfileValidationError("schema_version must be 1")

    username = _nonempty_string(payload.get("username"), "username")
    if not USERNAME_RE.fullmatch(username):
        raise ProfileValidationError("username is not a valid GitHub username")
    expected_source = f"https://github.com/users/{username}/contributions"
    if payload.get("source") != expected_source:
        raise ProfileValidationError(f"source must be {expected_source!r}")

    generated_at = _nonempty_string(payload.get("generated_at"), "generated_at")
    try:
        parsed_generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProfileValidationError("generated_at must be an ISO-8601 timestamp") from exc
    if parsed_generated_at.tzinfo is None:
        raise ProfileValidationError("generated_at must include a timezone")

    raw_days = payload.get("days")
    if not isinstance(raw_days, list):
        raise ProfileValidationError("days must be an array")
    if not MIN_CALENDAR_DAYS <= len(raw_days) <= MAX_CALENDAR_DAYS:
        raise ProfileValidationError(
            f"days must contain {MIN_CALENDAR_DAYS}–{MAX_CALENDAR_DAYS} calendar records"
        )
    days: list[tuple[date, int]] = []
    previous_day: date | None = None
    for index, raw_day in enumerate(raw_days):
        if not isinstance(raw_day, dict):
            raise ProfileValidationError(f"days[{index}] must be an object")
        parsed_day = _iso_date(raw_day.get("date"), f"days[{index}].date")
        if (
            previous_day is not None
            and parsed_day != previous_day + timedelta(days=1)
        ):
            raise ProfileValidationError(
                "days must be unique, strictly ordered, and consecutive"
            )
        previous_day = parsed_day
        count = _nonnegative_integer(raw_day.get("count"), f"days[{index}].count")
        level = _nonnegative_integer(raw_day.get("level"), f"days[{index}].level")
        if level > 4:
            raise ProfileValidationError(f"days[{index}].level must be between 0 and 4")
        if (count == 0) != (level == 0):
            raise ProfileValidationError(
                f"days[{index}] contribution count and level are inconsistent"
            )
        days.append((parsed_day, count))

    raw_range = payload.get("range")
    if not isinstance(raw_range, dict):
        raise ProfileValidationError("range must be an object")
    range_start = _iso_date(raw_range.get("start"), "range.start")
    range_end = _iso_date(raw_range.get("end"), "range.end")
    range_days = _positive_integer(raw_range.get("days"), "range.days")
    if range_start != days[0][0] or range_end != days[-1][0]:
        raise ProfileValidationError("range start/end must match the first/last day")
    if range_days != len(days):
        raise ProfileValidationError("range.days must match the number of day records")

    raw_stats = payload.get("stats")
    if not isinstance(raw_stats, dict):
        raise ProfileValidationError("stats must be an object")
    for field in ("yearly_total", "current_streak", "longest_streak"):
        _nonnegative_integer(raw_stats.get(field), f"stats.{field}")

    best_day = raw_stats.get("best_day")
    if best_day is not None:
        if not isinstance(best_day, dict):
            raise ProfileValidationError("stats.best_day must be an object or null")
        _iso_date(best_day.get("date"), "stats.best_day.date")
        _positive_integer(best_day.get("count"), "stats.best_day.count")

    monthly_totals = raw_stats.get("monthly_totals")
    if not isinstance(monthly_totals, dict):
        raise ProfileValidationError("stats.monthly_totals must be an object")
    for month, count in monthly_totals.items():
        if not MONTH_RE.fullmatch(month):
            raise ProfileValidationError(f"invalid monthly total key {month!r}")
        _nonnegative_integer(count, f"stats.monthly_totals.{month}")

    expected_stats = _calculated_stats(days)
    actual_stats = {
        "yearly_total": raw_stats.get("yearly_total"),
        "current_streak": raw_stats.get("current_streak"),
        "longest_streak": raw_stats.get("longest_streak"),
        "best_day": best_day,
        "monthly_totals": monthly_totals,
    }
    if actual_stats != expected_stats:
        mismatches = [
            field for field in expected_stats if actual_stats[field] != expected_stats[field]
        ]
        raise ProfileValidationError(
            "derived contribution stats do not match day records: " + ", ".join(mismatches)
        )
    return payload


def validate_identity_data(path: Path) -> Mapping[str, object]:
    """Validate the JSON contract consumed by the identity renderer."""

    payload = _load_json_object(path)
    for field in (
        "username",
        "display_name",
        "headline",
        "kicker",
        "now",
        "recognition",
        "education",
        "focus",
        "stack",
        "endpoint",
    ):
        _nonempty_string(payload.get(field), field)
    if not USERNAME_RE.fullmatch(str(payload["username"])):
        raise ProfileValidationError("username is not a valid GitHub username")

    roles = payload.get("roles")
    if not isinstance(roles, list) or len(roles) < 2:
        raise ProfileValidationError("roles must contain at least two entries")
    for index, role in enumerate(roles):
        _nonempty_string(role, f"roles[{index}]")

    stack_groups = payload.get("stack_groups")
    if not isinstance(stack_groups, list) or len(stack_groups) < 3:
        raise ProfileValidationError("stack_groups must contain at least three entries")
    for index, group in enumerate(stack_groups):
        if not isinstance(group, dict):
            raise ProfileValidationError(f"stack_groups[{index}] must be an object")
        for field in ("label", "value"):
            _nonempty_string(group.get(field), f"stack_groups[{index}].{field}")

    flagships = payload.get("flagships")
    if not isinstance(flagships, list) or len(flagships) < 3:
        raise ProfileValidationError("flagships must contain at least three entries")
    for index, project in enumerate(flagships):
        if not isinstance(project, dict):
            raise ProfileValidationError(f"flagships[{index}] must be an object")
        for field in ("code", "name", "status", "stack"):
            _nonempty_string(project.get(field), f"flagships[{index}].{field}")
    return payload


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def _check_url_text(value: str, context: str) -> None:
    if EXTERNAL_SCHEME_RE.search(value) or re.search(r"(^|[\s('\"])//[^\s/]+", value):
        raise ProfileValidationError(f"{context} contains an external URL")
    if re.search(r"@import\b", value, re.IGNORECASE):
        raise ProfileValidationError(f"{context} contains a CSS import")
    for match in URL_FUNCTION_RE.finditer(value):
        target = match.group(2).strip()
        if not target.startswith("#"):
            raise ProfileValidationError(f"{context} contains non-local url({target})")


def validate_svg(path: Path, *, expected_width: int = EXPECTED_SVG_WIDTH) -> ET.Element:
    """Parse and validate one accessible, passive, self-contained SVG."""

    try:
        source = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProfileValidationError(f"unable to read SVG {path}: {exc}") from exc
    if re.search(r"<!DOCTYPE\b|<!ENTITY\b|<\?xml-stylesheet\b", source, re.IGNORECASE):
        raise ProfileValidationError(f"{path} contains a forbidden declaration")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise ProfileValidationError(f"{path} is not well-formed XML: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise ProfileValidationError(f"{path} root element must be svg")
    width = root.attrib.get("width", "").strip()
    expected_width_re = re.compile(
        rf"^{re.escape(str(expected_width))}(?:\.0+)?(?:px)?$", re.IGNORECASE
    )
    if not expected_width_re.fullmatch(width):
        raise ProfileValidationError(f"{path} width must be {expected_width}px")
    if root.attrib.get("role", "").lower() != "img":
        raise ProfileValidationError(f"{path} must declare role=\"img\"")

    direct_titles = [node for node in root if _local_name(node.tag) == "title"]
    direct_descriptions = [node for node in root if _local_name(node.tag) == "desc"]
    if len(direct_titles) != 1 or not "".join(direct_titles[0].itertext()).strip():
        raise ProfileValidationError(f"{path} must have one non-empty top-level title")
    if len(direct_descriptions) != 1 or not "".join(direct_descriptions[0].itertext()).strip():
        raise ProfileValidationError(f"{path} must have one non-empty top-level desc")
    title_id = direct_titles[0].attrib.get("id", "")
    desc_id = direct_descriptions[0].attrib.get("id", "")
    labelled_by = root.attrib.get("aria-labelledby", "").split()
    if not title_id or not desc_id or title_id not in labelled_by or desc_id not in labelled_by:
        raise ProfileValidationError(
            f"{path} aria-labelledby must reference the title and desc IDs"
        )

    for element in root.iter():
        element_name = _local_name(element.tag)
        if element_name in {"script", "foreignobject"}:
            raise ProfileValidationError(f"{path} contains forbidden <{element_name}> content")
        for raw_name, value in element.attrib.items():
            attribute_name = _local_name(raw_name)
            if re.fullmatch(r"on[a-z][a-z0-9_.:-]*", attribute_name, re.IGNORECASE):
                raise ProfileValidationError(
                    f"{path} contains event-handler attribute {attribute_name!r}"
                )
            _check_url_text(value, f"{path} attribute {attribute_name}")
            if attribute_name in {"href", "src"} and value.strip() and not value.strip().startswith("#"):
                raise ProfileValidationError(
                    f"{path} attribute {attribute_name} references an external resource"
                )
        if element.text:
            _check_url_text(element.text, f"{path} <{element_name}> text")
        if element.tail:
            _check_url_text(element.tail, f"{path} XML text")
    return root


class _ImageSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        for name, value in attrs:
            if name.lower() == "src" and value:
                self.sources.append(value.strip())

    handle_startendtag = handle_starttag


def readme_image_sources(readme: str) -> set[str]:
    """Return HTML and common Markdown image destinations from README text."""

    sources = {
        (match.group(1) or match.group(2)).strip()
        for match in MARKDOWN_IMAGE_RE.finditer(readme)
    }
    definitions = {
        match.group(1).strip().casefold(): (match.group(2) or match.group(3)).strip()
        for match in REFERENCE_DEFINITION_RE.finditer(readme)
    }
    for match in REFERENCE_IMAGE_RE.finditer(readme):
        label = (match.group(2) or match.group(1)).strip().casefold()
        if label in definitions:
            sources.add(definitions[label])

    html_parser = _ImageSourceParser()
    html_parser.feed(readme)
    html_parser.close()
    sources.update(html_parser.sources)
    return {source for source in sources if source}


def validate_readme_images(readme_path: Path, *, repository_root: Path | None = None) -> list[Path]:
    """Ensure every repository-local README image resolves to an existing file."""

    try:
        readme = readme_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProfileValidationError(f"unable to read {readme_path}: {exc}") from exc
    root = (repository_root or readme_path.parent).resolve()
    resolved_images: list[Path] = []
    missing: list[str] = []
    invalid: list[str] = []
    for source in sorted(readme_image_sources(readme)):
        parsed = urlsplit(source)
        if parsed.scheme or parsed.netloc or source.startswith("//") or source.startswith("#"):
            continue
        raw_path = unquote(parsed.path)
        if not raw_path:
            continue
        candidate = (
            root / raw_path.lstrip("/\\")
            if raw_path.startswith(("/", "\\"))
            else readme_path.parent / raw_path
        ).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            invalid.append(source)
            continue
        if not candidate.is_file():
            missing.append(source)
        else:
            resolved_images.append(candidate)
    if invalid:
        raise ProfileValidationError(
            "README local image references escape the repository: " + ", ".join(invalid)
        )
    if missing:
        raise ProfileValidationError(
            "README local image references do not exist: " + ", ".join(missing)
        )
    return resolved_images


def run_validation(
    contributions: Path,
    profile_data: Path,
    portrait_svg: Path,
    info_card_svg: Path,
    heatmap_svg: Path,
    readme: Path,
) -> list[str]:
    """Run every validation and return all failures rather than stopping early."""

    checks: list[tuple[str, Callable[[], object]]] = [
        ("contribution data", lambda: validate_contribution_data(contributions)),
        ("identity data", lambda: validate_identity_data(profile_data)),
        ("portrait SVG", lambda: validate_svg(portrait_svg, expected_width=840)),
        ("info card SVG", lambda: validate_svg(info_card_svg, expected_width=480)),
        ("heatmap SVG", lambda: validate_svg(heatmap_svg, expected_width=888)),
        (
            "README images",
            lambda: validate_readme_images(readme, repository_root=readme.parent),
        ),
    ]
    failures: list[str] = []
    for label, check in checks:
        try:
            check()
        except ProfileValidationError as exc:
            failures.append(f"{label}: {exc}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contributions", type=Path, default=DEFAULT_CONTRIBUTIONS)
    parser.add_argument("--profile-data", type=Path, default=DEFAULT_PROFILE_DATA)
    parser.add_argument("--portrait-svg", type=Path, default=DEFAULT_PORTRAIT_SVG)
    parser.add_argument("--info-card-svg", type=Path, default=DEFAULT_INFO_CARD_SVG)
    parser.add_argument("--heatmap-svg", type=Path, default=DEFAULT_HEATMAP_SVG)
    parser.add_argument("--readme", type=Path, default=DEFAULT_README)
    args = parser.parse_args(argv)

    failures = run_validation(
        args.contributions,
        args.profile_data,
        args.portrait_svg,
        args.info_card_svg,
        args.heatmap_svg,
        args.readme,
    )
    if failures:
        for failure in failures:
            print(f"error: {failure}", file=sys.stderr)
        return 1
    print("Profile validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
