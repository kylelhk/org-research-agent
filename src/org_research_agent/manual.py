"""Load organisations added by hand and combine them with the map list."""

from __future__ import annotations

import tomllib
from pathlib import Path

from org_research_agent.organisation import UNKNOWN, Organisation

DEFAULT_MANUAL_PATH = Path("config/manual_organisations.private.toml")


class ManualListError(Exception):
    """Raised when the hand-added list cannot be used."""


def load_manual(path: Path | str = DEFAULT_MANUAL_PATH) -> list[Organisation]:
    """Read hand-added organisations. A missing file simply means there are none."""
    path = Path(path)
    if not path.is_file():
        return []

    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ManualListError(f"Manual list is not valid TOML: {error}") from error

    entries = data.get("organisation", [])
    if not isinstance(entries, list):
        raise ManualListError("Use [[organisation]] tables in the manual list.")

    organisations = []
    for number, entry in enumerate(entries, start=1):
        name = entry.get("name", "").strip() if isinstance(entry, dict) else ""
        if not name:
            raise ManualListError(f"Organisation {number} in the manual list has no name.")
        organisations.append(
            Organisation(
                name=name,
                type=entry.get("type", UNKNOWN),
                suburb=entry.get("suburb", UNKNOWN),
                website=entry.get("website", ""),
                source="manual",
            )
        )
    return organisations


def combine(osm: list[Organisation], manual: list[Organisation]) -> list[Organisation]:
    """Merge both lists by name. If an organisation is in both, the manual entry wins."""
    merged = {org.name.lower(): org for org in osm}
    merged.update({org.name.lower(): org for org in manual})
    return sorted(merged.values(), key=lambda org: org.name.lower())


def check_minimum(organisations: list[Organisation], minimum: int) -> None:
    """Stop early if there are too few organisations to meet the project target."""
    if len(organisations) < minimum:
        raise ManualListError(
            f"Only {len(organisations)} organisations found; the minimum is {minimum}. "
            "Add more to the manual list."
        )
