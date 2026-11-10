"""Summarise the fetch log of a run: which pages were read, and which requests were refused.

The fetch tool writes one line to the log for every request the agent makes. After each
organisation, the research step reads the new lines and reports what happened, so a
person can see at a glance if the agent asked for something it may not read.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PAGES_READ = "pages_read"
OTHER_WEBSITES = "other_websites"
PROFILE_PAGES = "profile_pages"
TEAM_PAGES = "team_pages"
ROBOTS = "robots"
PAGE_CAP = "page_cap"
ERRORS = "errors"

OUTCOME_GROUPS = {
    "fetched": PAGES_READ,
    "blocked: off-site": OTHER_WEBSITES,
    "blocked: off-site redirect": OTHER_WEBSITES,
    "blocked: staff profile page": PROFILE_PAGES,
    "blocked: team page": TEAM_PAGES,
    "blocked: robots.txt": ROBOTS,
    "blocked: page cap": PAGE_CAP,
}


def read_entries(path: Path | str, start: int = 0) -> list[dict]:
    """Read the log lines from line number `start` onwards. A missing log means none."""
    path = Path(path)
    if not path.is_file():
        return []
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    return [json.loads(line) for line in lines[start:]]


def count_lines(path: Path | str) -> int:
    path = Path(path)
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def summarise(entries: list[dict]) -> dict[str, int]:
    """Count the log entries by what happened to each request."""
    counts: Counter[str] = Counter()
    for entry in entries:
        outcome = entry.get("outcome", "")
        if outcome in OUTCOME_GROUPS:
            counts[OUTCOME_GROUPS[outcome]] += 1
        elif outcome.startswith("error"):
            counts[ERRORS] += 1
    return dict(counts)


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def describe_refusals(counts: dict[str, int]) -> str:
    """One sentence about requests the safeguards refused, or "" if there were none.

    Hitting the page cap is normal, so it is left out. So is a team page: they are
    blocked by design, and an agent following links will often try one. Asking for
    another website, a
    staff profile page, or a page robots.txt forbids is worth a person's attention.
    """
    parts = []
    if counts.get(OTHER_WEBSITES):
        parts.append(
            _plural(
                counts[OTHER_WEBSITES],
                "request for another website",
                "requests for another website",
            )
        )
    if counts.get(PROFILE_PAGES):
        parts.append(_plural(counts[PROFILE_PAGES], "staff profile page"))
    if counts.get(ROBOTS):
        parts.append(
            _plural(counts[ROBOTS], "page blocked by robots.txt", "pages blocked by robots.txt")
        )
    if not parts:
        return ""
    return "refused by the safeguards: " + ", ".join(parts)


def total(results_counts: list[dict[str, int]]) -> dict[str, int]:
    """Add up the counts for a whole run."""
    combined: Counter[str] = Counter()
    for counts in results_counts:
        combined.update(counts)
    return dict(combined)
