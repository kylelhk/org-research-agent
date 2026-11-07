"""A shared record for an organisation to be researched."""

from __future__ import annotations

from dataclasses import dataclass

UNKNOWN = "unknown"


@dataclass(frozen=True)
class Organisation:
    name: str
    type: str = UNKNOWN
    suburb: str = UNKNOWN
    website: str = ""
    source: str = "osm"  # Either "osm" or "manual".
