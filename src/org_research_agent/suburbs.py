"""Choose the suburbs for a run, and check that typed suburbs are in Perth.

The settings file lists the usual suburbs. Before each run from the launcher, a
small window lets the user untick any of them and type others. A typed suburb is
looked up on OpenStreetMap's place search (only the suburb name is sent), which
also gives the centre point for that suburb's map search.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from org_research_agent.osm import USER_AGENT

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# OpenStreetMap's place search allows one request a second.
SEARCH_GAP_S = 1.1
# A box around the Perth metropolitan area, from Two Rocks to Singleton and the hills.
PERTH_BOUNDS = (-32.50, -31.45, 115.60, 116.35)  # south, north, west, east

Point = tuple[float, float]


class PlaceSearchError(Exception):
    """Raised when the place search can't be reached."""


@dataclass(frozen=True)
class Place:
    name: str
    centre: Point


@dataclass(frozen=True)
class Selection:
    """The suburbs chosen for one run, and the centre points for the map search."""

    suburbs: tuple[str, ...]
    centres: tuple[Point, ...]
    # True when at least one of the settings' own suburbs is included, so the
    # hand-added list and the nearby suburbs still apply.
    includes_usual: bool
    # True when the choice is exactly the settings' suburbs, nothing more or less.
    is_usual: bool
    not_found: tuple[str, ...] = field(default=())
    # What each centre point is for, such as "Subiaco", to show the map search's progress.
    centre_labels: tuple[str, ...] = field(default=())


# Short forms people type, and the official form used in place names. Single letters
# are only read this way at the start of a name, as in "E Victoria Park".
_LONG_FORMS = {"st": "St", "saint": "St", "mt": "Mount", "nth": "North", "sth": "South"}
_START_FORMS = {"e": "East", "w": "West", "n": "North", "s": "South"}
_LOCAL_FORMS = {"vic": "Victoria"}
# Commas separate suburbs; semicolons, slashes, and new lines are accepted too.
_SEPARATORS = re.compile(r"[,;/\n]+")
# A state, postcode, or country typed after a suburb, as in "Bentley WA 6102".
_TRAILING = re.compile(r"(?:\s+(?:wa|w\.a\.|western australia|australia|\d{4}))+$", re.I)
_NOT_SUBURBS = {"wa", "w.a.", "western australia", "australia"}
# More typed suburbs than this asks first, since each adds its own map search.
MANY_SUBURBS = 5


def _cap(word: str) -> str:
    """Capitalise each part of a word, as in O'Connor."""
    return "'".join(part[:1].upper() + part[1:].lower() for part in word.split("'"))


def tidy_name(name: str) -> str:
    """The official way to write a typed suburb: "mt. lawley" becomes "Mount Lawley".

    Words are capitalised only when the whole name was typed in one case, so a name
    typed with its own capitals, such as "McKenzie", keeps them.
    """
    name = name.replace("\u2019", "'").replace("\u2018", "'").replace(".", " ")
    words = name.split()
    one_case = name == name.lower() or name == name.upper()
    tidied = []
    for number, word in enumerate(words):
        lower = word.lower()
        if lower in _LONG_FORMS:
            tidied.append(_LONG_FORMS[lower])
        elif number == 0 and len(words) > 1 and lower in _START_FORMS:
            tidied.append(_START_FORMS[lower])
        elif lower in _LOCAL_FORMS:
            tidied.append(_LOCAL_FORMS[lower])
        else:
            tidied.append(_cap(word) if one_case else word)
    return " ".join(tidied)


def suburb_key(name: str) -> str:
    """A key for comparing suburb names, ignoring case, full stops, apostrophes, dashes,
    and short forms, so "St. James", "Saint James", and "st james" all match."""
    tidied = tidy_name(name).lower().replace("'", "")
    return " ".join(re.sub(r"[\u2010-\u2015-]", " ", tidied).split())


def parse_others(text: str) -> list[str]:
    """Split the Others box into suburbs, tidy each one, and drop blanks and repeats.

    A state, postcode, or country after a name is dropped, as in "Bentley WA 6102".
    """
    seen: set[str] = set()
    names = []
    for part in _SEPARATORS.split(text):
        name = _TRAILING.sub("", " ".join(part.split())).strip(" .")
        if not name or name.lower() in _NOT_SUBURBS or name.isdigit():
            continue
        name = tidy_name(name)
        if suburb_key(name) not in seen:
            seen.add(suburb_key(name))
            names.append(name)
    return names


def _in_perth(lat: float, lon: float) -> bool:
    south, north, west, east = PERTH_BOUNDS
    return south <= lat <= north and west <= lon <= east


def _fetch_places(name: str, timeout: int = 20) -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "q": f"{tidy_name(name)}, Western Australia",
            "format": "jsonv2",
            "countrycodes": "au",
            "featureType": "settlement",
            "limit": 10,
        }
    )
    request = urllib.request.Request(f"{NOMINATIM_URL}?{query}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.load(response)
    except (OSError, ValueError) as error:
        raise PlaceSearchError(f"The place search couldn't be reached ({error}).") from error


def locate_suburb(name: str, fetch: Callable[[str], list[dict]] = _fetch_places) -> Place | None:
    """Find a Perth suburb by name. Returns None if there's no such suburb in Perth."""
    wanted = suburb_key(name)
    for result in fetch(name):
        try:
            lat, lon = float(result["lat"]), float(result["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if suburb_key(result.get("name") or "") == wanted and _in_perth(lat, lon):
            return Place(name=result["name"].strip(), centre=(lat, lon))
    return None


class SuburbPrompt(Protocol):
    """What the suburb window does, so the rules can be tested without a screen."""

    def ask(self) -> tuple[list[str], str] | None: ...
    def warn(self, message: str) -> None: ...
    def confirm(self, message: str) -> bool: ...
    def busy(self, busy: bool) -> None: ...


def _join(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def build_selection(
    usual: Sequence[str],
    usual_centre: Point | None,
    ticked: Sequence[str],
    others: Sequence[Place | str],
    locate: Callable[[str], Place | None] = locate_suburb,
    pause: Callable[[float], None] = time.sleep,
) -> Selection:
    """Turn the chosen suburbs into the run's suburbs and map centre points.

    When every usual suburb is ticked, the settings' own centre point covers them,
    so a usual run searches exactly as before. Otherwise each ticked suburb is
    looked up for its own centre. A typed suburb that wasn't found has no centre:
    it still counts as part of the area, but has no map search of its own.
    """
    ticked = [name for name in usual if name in ticked]
    centres: list[Point] = []
    labels: list[str] = []
    if ticked and len(ticked) == len(usual) and usual_centre is not None:
        centres.append(usual_centre)
        labels.append(_join(ticked))
    else:
        for number, name in enumerate(ticked):
            if number:
                pause(SEARCH_GAP_S)
            try:
                place = locate(name)
            except PlaceSearchError:
                place = None
            if place:
                centres.append(place.centre)
                labels.append(name)
            elif usual_centre is not None and usual_centre not in centres:
                centres.append(usual_centre)
                labels.append(_join(usual))
    suburbs = list(ticked)
    not_found = []
    for other in others:
        if isinstance(other, Place):
            suburbs.append(other.name)
            centres.append(other.centre)
            labels.append(other.name)
        else:
            suburbs.append(other)
            not_found.append(other)
    return Selection(
        suburbs=tuple(suburbs),
        centres=tuple(centres),
        includes_usual=bool(ticked),
        is_usual=ticked == list(usual) and not others,
        not_found=tuple(not_found),
        centre_labels=tuple(labels),
    )


def _drop_repeats(found: Sequence[Place | str], usual_keys: dict[str, str]) -> list:
    """Drop typed suburbs that turn out to be a usual suburb or another typed one."""
    seen = set(usual_keys)
    kept = []
    for item in found:
        key = suburb_key(item.name if isinstance(item, Place) else item)
        if key not in seen:
            seen.add(key)
            kept.append(item)
    return kept


def choose_suburbs(
    usual: Sequence[str],
    usual_centre: Point | None,
    prompt: SuburbPrompt,
    locate: Callable[[str], Place | None] = locate_suburb,
    pause: Callable[[float], None] = time.sleep,
) -> Selection | None:
    """Ask for the suburbs until the choice is valid. Returns None if cancelled."""
    usual_keys = {suburb_key(name): name for name in usual}
    while True:
        answer = prompt.ask()
        if answer is None:
            return None
        ticked, text = answer
        typed = parse_others(text)

        repeated = [usual_keys[suburb_key(n)] for n in typed if suburb_key(n) in usual_keys]
        if repeated:
            prompt.warn(
                f"{_join(repeated)} {'is' if len(repeated) == 1 else 'are'} already "
                "in the tickboxes above. Please remove "
                f"{'it' if len(repeated) == 1 else 'them'} from Others, and use the "
                "tickbox instead."
            )
            continue
        if not ticked and not typed:
            prompt.warn("Please tick a suburb or type one in Others.")
            continue
        if len(typed) > MANY_SUBURBS and not prompt.confirm(
            f"You've added {len(typed)} suburbs. Each one adds its own map search, so the "
            "run will take longer and use more of your Claude allowance.\n\n"
            "Do you want to go ahead?"
        ):
            continue

        prompt.busy(True)
        found: list[Place | str] = []
        missing: list[str] = []
        unchecked: list[str] = []
        for number, name in enumerate(typed):
            if number:
                pause(SEARCH_GAP_S)
            try:
                place = locate(name)
            except PlaceSearchError:
                unchecked.append(name)
                found.append(name)
                continue
            if place:
                found.append(place)
            else:
                missing.append(name)
                found.append(name)
        prompt.busy(False)

        found = _drop_repeats(found, usual_keys)
        if missing and not prompt.confirm(
            f"{_join(missing)} wasn't found in Perth. Check the spelling.\n\n"
            "Do you still want to search with "
            f"{'it' if len(missing) == 1 else 'them'}?"
        ):
            continue
        if unchecked and not prompt.confirm(
            f"{_join(unchecked)} couldn't be checked just now. Check the internet "
            "connection.\n\nDo you still want to search with "
            f"{'it' if len(unchecked) == 1 else 'them'}?"
        ):
            continue
        prompt.busy(True)
        try:
            return build_selection(usual, usual_centre, ticked, found, locate, pause)
        finally:
            prompt.busy(False)
