#!/usr/bin/env python3
"""Fetch the user's public pull requests in repositories they do not own.

Uses GitHub's search API (``GET /search/issues``), which needs no token for
public data; when ``GITHUB_TOKEN`` is set (GitHub Actions provides one for the
workflow, no personal access token is involved) it is sent to lift the rate
limit.  Standard library only, so the daily workflow stays small.

Output: ``data/upstream_prs.json`` with the merged, open and closed counts,
a per-repository tally, and the latest merged and open PRs.  The write is
atomic; on any failure the previous file is left untouched and the exit code
is 1, as ``fetch_contributions.py`` does.

Honesty notes recorded in the JSON: the owner filter is a heuristic (the user
and their own organisations are excluded), search returns at most 1000 items,
and the index can lag a merge by minutes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "data" / "upstream_prs.json"
DEFAULT_USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER", "mertefesensoy")
SEARCH_URL = "https://api.github.com/search/issues"
PAGE_SIZE = 100
MAX_PAGES = 10  # GitHub search returns at most 1000 results
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
LATEST_MERGED = 12
LATEST_OPEN = 8

# The user and the organisations they own or run.  PRs there are not
# "upstream" contributions.  Same heuristic as the OSS HQ tracker.
EXCLUDED_OWNERS = frozenset(
    owner.lower()
    for owner in (
        "mertefesensoy",
        "Cassandra-Collective",
        "SuperconducTED",
        "The-Open-Memory-Initiative-OMI",
        "BeeLink-CN",
        "DietHuzz",
        "Gumeus",
        "NeuroTie",
    )
)


class UpstreamError(RuntimeError):
    """Raised when the search API cannot be read or its payload is malformed."""


def _request(url: str, token: str | None) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mertefesensoy-profile-ledger",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise UpstreamError(f"GitHub search returned HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise UpstreamError(f"unable to reach GitHub search: {exc.reason}") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise UpstreamError("GitHub search response exceeded the size limit")
    return body


def search_pull_requests(username: str, token: str | None = None) -> list[dict[str, object]]:
    """Return every public PR authored by ``username`` that search will give us."""

    query = quote(f"is:pr author:{username} is:public", safe=":")
    items: list[dict[str, object]] = []
    for page in range(1, MAX_PAGES + 1):
        url = (
            f"{SEARCH_URL}?q={query}&per_page={PAGE_SIZE}&page={page}"
            "&sort=updated&order=desc&advanced_search=true"
        )
        try:
            payload = json.loads(_request(url, token).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpstreamError(f"GitHub search returned invalid JSON: {exc}") from exc
        page_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(page_items, list):
            raise UpstreamError("GitHub search payload has no items array")
        items.extend(item for item in page_items if isinstance(item, dict))
        total = payload.get("total_count")
        if len(page_items) < PAGE_SIZE or (isinstance(total, int) and len(items) >= total):
            break
    return items


def _repo_from_item(item: Mapping[str, object]) -> str | None:
    repository_url = item.get("repository_url")
    if not isinstance(repository_url, str):
        return None
    path = urlsplit(repository_url).path.strip("/")
    parts = path.split("/")
    if len(parts) != 3 or parts[0] != "repos":
        return None
    return f"{parts[1]}/{parts[2]}"


def _iso_day(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def normalize(
    items: Iterable[Mapping[str, object]],
    *,
    excluded_owners: frozenset[str] = EXCLUDED_OWNERS,
) -> list[dict[str, object]]:
    """Reduce search items to the ledger's record shape, dropping own-org PRs."""

    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in items:
        repo = _repo_from_item(item)
        if repo is None:
            continue
        owner = repo.split("/", 1)[0].lower()
        if owner in excluded_owners:
            continue
        html_url = item.get("html_url")
        number = item.get("number")
        title = item.get("title")
        if not isinstance(html_url, str) or not isinstance(number, int) or not isinstance(title, str):
            continue
        key = f"{repo}#{number}"
        if key in seen:
            continue
        seen.add(key)
        pull = item.get("pull_request")
        merged_at = _iso_day(pull.get("merged_at")) if isinstance(pull, dict) else None
        if merged_at:
            state = "merged"
        elif item.get("state") == "open":
            state = "open"
        else:
            state = "closed"
        records.append(
            {
                "repo": repo,
                "number": number,
                "title": " ".join(title.split()),
                "url": html_url,
                "state": state,
                "draft": bool(item.get("draft", False)),
                "created": _iso_day(item.get("created_at")),
                "merged": merged_at,
                "closed": _iso_day(item.get("closed_at")),
            }
        )
    return records


def build_payload(
    username: str,
    records: Sequence[Mapping[str, object]],
    *,
    generated_at: datetime | None = None,
    excluded_owners: frozenset[str] = EXCLUDED_OWNERS,
) -> dict[str, object]:
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    generated_at = generated_at.astimezone(timezone.utc).replace(microsecond=0)

    per_repo: dict[str, dict[str, int]] = {}
    counts = {"merged": 0, "open": 0, "closed": 0}
    for record in records:
        state = str(record["state"])
        counts[state] += 1
        tally = per_repo.setdefault(str(record["repo"]), {"merged": 0, "open": 0, "closed": 0})
        tally[state] += 1

    merged = sorted(
        (r for r in records if r["state"] == "merged"),
        key=lambda r: (str(r["merged"]), int(r["number"])),
        reverse=True,
    )
    open_prs = sorted(
        (r for r in records if r["state"] == "open"),
        key=lambda r: (str(r["created"]), int(r["number"])),
        reverse=True,
    )
    repositories = sorted(
        ({"repo": repo, **tally} for repo, tally in per_repo.items()),
        key=lambda entry: (-entry["merged"], -entry["open"], entry["repo"].lower()),
    )
    return {
        "schema_version": 1,
        "username": username,
        "source": SEARCH_URL,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "excluded_owners": sorted(excluded_owners),
        "caveats": [
            "Public pull requests authored by the user in repositories not owned by the user or their organisations.",
            "GitHub search returns at most 1000 results and can lag a merge by minutes.",
            "Whether a PR counts for any programme is decided by that programme, not by this ledger.",
        ],
        "stats": {
            **counts,
            "repositories": len(per_repo),
            "last_merged": merged[0]["merged"] if merged else None,
        },
        "repositories": repositories,
        "merged": [dict(r) for r in merged[:LATEST_MERGED]],
        "open": [dict(r) for r in open_prs[:LATEST_OPEN]],
    }


def write_json_atomic(payload: Mapping[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary_name = temporary.name
        os.replace(temporary_name, output)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch upstream pull requests as normalized JSON.")
    parser.add_argument("username", nargs="?", default=DEFAULT_USERNAME)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--items-file",
        type=Path,
        help="read a saved search payload (JSON with an items array) instead of calling GitHub",
    )
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN") or None

    try:
        if args.items_file:
            saved = json.loads(args.items_file.read_text(encoding="utf-8"))
            items = saved.get("items", []) if isinstance(saved, dict) else saved
        else:
            items = search_pull_requests(args.username, token)
        records = normalize(items)
        payload = build_payload(args.username, records)
        write_json_atomic(payload, args.output)
    except (UpstreamError, OSError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stats = payload["stats"]
    assert isinstance(stats, dict)
    print(
        f"wrote {stats['merged']} merged / {stats['open']} open upstream PRs across "
        f"{stats['repositories']} repositories to {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
