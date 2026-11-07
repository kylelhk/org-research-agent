"""Find nearby health organisations in OpenStreetMap through the Overpass API.

Only public map data about organisations is used here. Nothing about
individual people is requested or kept.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from org_research_agent.organisation import UNKNOWN, Organisation

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "org-research-agent/0.1 (learning project)"

AMENITY_TYPES = {
    "doctors": "GP clinic",
    "clinic": "clinic",
    "dentist": "dental practice",
    "pharmacy": "pharmacy",
}

HEALTHCARE_TYPES = {
    "doctor": "GP clinic",
    "dentist": "dental practice",
    "pharmacy": "pharmacy",
    "physiotherapist": "physiotherapy",
    "chiropractor": "chiropractic",
    "podiatrist": "allied health",
    "occupational_therapist": "allied health",
    "speech_therapist": "allied health",
    "psychotherapist": "allied health",
    "osteopath": "allied health",
}


def build_query(lat: float, lon: float, radius_m: int) -> str:
    """Build an Overpass query for health-related places around a point."""
    amenities = "|".join(AMENITY_TYPES)
    healthcare = "|".join(HEALTHCARE_TYPES)
    around = f"(around:{radius_m},{lat},{lon})"
    return (
        "[out:json][timeout:60];"
        "("
        f'nwr{around}["amenity"~"^({amenities})$"];'
        f'nwr{around}["healthcare"~"^({healthcare})$"];'
        ");"
        "out tags center;"
    )


def fetch_elements(query: str, url: str = OVERPASS_URL, timeout: int = 90) -> list[dict]:
    """Send a query to Overpass and return the raw elements."""
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.load(response).get("elements", [])


def _type_from_tags(tags: dict) -> str:
    if tags.get("healthcare") in HEALTHCARE_TYPES:
        return HEALTHCARE_TYPES[tags["healthcare"]]
    if tags.get("amenity") in AMENITY_TYPES:
        return AMENITY_TYPES[tags["amenity"]]
    return UNKNOWN


def parse_elements(elements: list[dict]) -> list[Organisation]:
    """Turn raw map elements into organisations, skipping unnamed and duplicate ones."""
    seen: set[str] = set()
    organisations = []
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name", "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        organisations.append(
            Organisation(
                name=name,
                type=_type_from_tags(tags),
                suburb=tags.get("addr:suburb", UNKNOWN),
                website=tags.get("website") or tags.get("contact:website", ""),
            )
        )
    return sorted(organisations, key=lambda org: org.name.lower())


def find_organisations(lat: float, lon: float, radius_m: int = 3000) -> list[Organisation]:
    """Look up nearby organisations from OpenStreetMap."""
    return parse_elements(fetch_elements(build_query(lat, lon, radius_m)))
