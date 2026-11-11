"""Find a missing or broken website for an organisation with the Brave Search API.

This runs before the agent, in plain Python, and changes nothing about how the
agent researches a website. For each organisation it:

1. Searches for the organisation's name, and keeps only the result addresses.
   Titles and snippets are thrown away unread, so no personal information from
   search results is kept, logged, or passed to the AI.
2. Skips directories and social media, such as Facebook or HotDoc.
3. Opens each remaining home page with the same rules as the agent's fetch tool
   (robots.txt, no off-site redirects, no team pages), and accepts it only if the
   page names the organisation and mentions the local area, and the name is also
   in the page title or the web address. A directory page that lists the
   practice among others fails that last test.

The page text is checked here and then discarded: it never goes to the AI.
An API key is needed in the BRAVE_API_KEY environment variable.

Search results vary from one run to the next, so each confirmed website is saved
(config/found_websites.private.json, git-ignored). Later runs check the saved site
still works and reuse it without searching. Only practice names and their public
website addresses are saved.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from org_research_agent.fetcher import PageFetcher, normalise_host
from org_research_agent.organisation import UNKNOWN, Organisation

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
API_KEY_VARIABLE = "BRAVE_API_KEY"
RESULTS_PER_SEARCH = 10
CANDIDATES_TO_OPEN = 4
SEARCH_GAP_S = 1.1  # Stay well under the API's rate limit.
FOUND, CHECKED, NOT_FOUND = "found", "listed site works", "not found"
SAVED = "saved from an earlier search"
DEFAULT_SAVED_PATH = Path("config/found_websites.private.json")

# Sites that list many businesses. A practice's page there is not its own website.
DIRECTORY_HOSTS = (
    "facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com",
    "youtube.com", "tiktok.com", "google.com", "goo.gl", "apple.com", "bing.com",
    "yelp.com", "yelp.com.au", "yellowpages.com.au", "truelocal.com.au",
    "localsearch.com.au", "startlocal.com.au", "hotfrog.com.au", "cylex.com.au",
    "healthengine.com.au", "hotdoc.com.au", "healthdirect.gov.au", "whitecoat.com.au",
    "ratemds.com", "doctoroo.com.au", "findapharmacy.com.au", "hipages.com.au",
    "seek.com.au", "indeed.com", "au.indeed.com", "wikipedia.org", "tripadvisor.com.au",
    "nearmeau.com", "cybo.com", "wheree.com", "au.nearbymedical.com", "abr.business.gov.au",
    "place-advisor.com", "chemistnear.me",
)  # fmt: skip
# Words too common in practice names to show that a page is about this one.
COMMON_WORDS = {
    "the", "and", "of", "at", "in", "on", "for", "pty", "ltd", "co", "group", "centre",
    "center", "clinic", "medical", "dental", "health", "healthcare", "practice", "pharmacy",
    "chemist", "physio", "physiotherapy", "gp", "family", "after", "hours", "care",
    "services", "wa", "perth",
}  # fmt: skip
WORD = re.compile(r"[a-z0-9]+")


class WebsiteLookupError(Exception):
    """The website lookup could not run, for example because the API key is missing."""


@dataclass(frozen=True)
class LookupResult:
    organisation: Organisation
    outcome: str  # FOUND, CHECKED, or NOT_FOUND
    searches: int = 0


def _words(text: str) -> list[str]:
    return WORD.findall(text.lower().replace("&", " and "))


def distinctive_words(name: str) -> list[str]:
    """The words in a name that set it apart, such as "aardent" in "Aardent Dental"."""
    words = [w for w in _words(name) if w not in COMMON_WORDS and len(w) > 1]
    return words or _words(name)


def names_organisation(page_text: str, name: str) -> bool:
    """True if the page uses the organisation's distinctive words.

    All of them for a short name, and at least two thirds for a longer one, so
    "South Perth Medical Centre & After Hours GP" still matches a site that calls
    itself "South Perth Medical Centre".
    """
    wanted = distinctive_words(name)
    present = set(_words(page_text))
    found = sum(word in present for word in wanted)
    if len(wanted) <= 2:
        return found == len(wanted)
    return found * 3 >= len(wanted) * 2


def mentions_area(page_text: str, places: Iterable[str]) -> bool:
    """True if the page mentions one of the local places, as whole words."""
    text = " ".join(_words(page_text))
    return any(re.search(rf"\b{' '.join(_words(place))}\b", text) for place in places if place)


def is_own_site(title: str, url: str, name: str, places: Iterable[str]) -> bool:
    """True if the title or web address carries the name, as a practice's own site does.

    A name made only of place words, such as "Victoria Park Dental Centre", could be
    any local practice describing itself, so its web address must carry the name.
    """
    place_words = {w for place in places for w in _words(place)}
    wanted = distinctive_words(name)
    own = [w for w in wanted if w not in place_words]
    host = "".join(_words(normalise_host(urlsplit(url).hostname or "")))
    if not own:
        return "".join(wanted) in host
    return names_organisation(title, name) or any(w in host for w in own if len(w) >= 4)


def is_directory(url: str) -> bool:
    host = normalise_host(urlsplit(url).hostname or "")
    return any(host == d or host.endswith("." + d) for d in DIRECTORY_HOSTS)


def home_page(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


def brave_search(query: str, api_key: str, timeout: int = 20) -> list[str]:
    """Return only the result addresses for a search. Everything else is dropped."""
    params = urllib.parse.urlencode(
        {"q": query, "count": RESULTS_PER_SEARCH, "country": "AU", "safesearch": "strict"}
    )
    request = urllib.request.Request(
        f"{BRAVE_URL}?{params}",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    results = data.get("web", {}).get("results", [])
    return [r["url"] for r in results if isinstance(r, dict) and isinstance(r.get("url"), str)]


def _page_text(url: str, allowed_terms: tuple[str, ...] = ()) -> str:
    """A home page's text, read under the fetch tool's rules, or "" if it can't be read.

    The organisation's name and places are passed so the name masking leaves them be.
    """
    host = urlsplit(url).hostname or ""
    text = PageFetcher(host, max_pages=1, allowed_terms=allowed_terms).fetch(url)
    return "" if text.startswith(("BLOCKED", "ERROR")) else text


def _confirms(url: str, org: Organisation, places: tuple[str, ...], read: Callable) -> bool:
    text = read(url)
    title = next((line[12:] for line in text.splitlines() if line.startswith("Page title: ")), "")
    return (
        bool(text)
        and names_organisation(text, org.name)
        and mentions_area(text, places)
        and is_own_site(title, url, org.name, places)
    )


def _key(org: Organisation) -> str:
    return " ".join(_words(org.name))


def load_saved(path: Path) -> dict[str, dict]:
    """Websites confirmed in earlier runs, by organisation name. Empty if none yet."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def find_website(
    org: Organisation,
    places: tuple[str, ...],
    api_key: str,
    search: Callable[[str, str], list[str]] = brave_search,
    read: Callable[[str], str] | None = None,
    saved_url: str | None = None,
) -> LookupResult:
    """Keep a listed or saved website that works, or search for one the page confirms."""
    read = read or (lambda url: _page_text(url, (org.name, *places)))
    if org.website and _confirms(home_page(org.website), org, places, read):
        return LookupResult(org, CHECKED)
    if saved_url and _confirms(saved_url, org, places, read):
        return LookupResult(replace(org, website=saved_url), SAVED)
    where = org.suburb if org.suburb != UNKNOWN else "Perth"
    urls = search(f'"{org.name}" {where} WA', api_key)
    seen: set[str] = set()
    for url in urls:
        if is_directory(url) or urlsplit(url).scheme not in {"http", "https"}:
            continue
        home = home_page(url)
        if home in seen:
            continue
        seen.add(home)
        if len(seen) > CANDIDATES_TO_OPEN:
            break
        if _confirms(home, org, places, read):
            return LookupResult(replace(org, website=home), FOUND, 1)
    return LookupResult(org, NOT_FOUND, 1)


def _search_with_retry(
    search: Callable[[str, str], list[str]], pause: Callable[[float], None]
) -> Callable[[str, str], list[str]]:
    """Retry a failed search once after a pause, and stop the run if the key is refused."""

    def wrapped(query: str, api_key: str) -> list[str]:
        for attempt in (1, 2):
            try:
                return search(query, api_key)
            except urllib.error.HTTPError as error:
                if error.code in {401, 403}:
                    raise WebsiteLookupError(
                        f"The search service refused the API key (HTTP {error.code})."
                    ) from error
                if attempt == 2:
                    raise
            except (urllib.error.URLError, OSError, ValueError):
                if attempt == 2:
                    raise
            pause(3)
        return []

    return wrapped


def find_websites(
    organisations: list[Organisation],
    places: tuple[str, ...],
    api_key: str | None = None,
    search: Callable[[str, str], list[str]] = brave_search,
    read: Callable[[str], str] | None = None,
    pause: Callable[[float], None] = time.sleep,
    saved_path: Path | None = DEFAULT_SAVED_PATH,
) -> list[LookupResult]:
    """Run find_website for each organisation, one search at a time, and save new finds."""
    api_key = api_key or os.environ.get(API_KEY_VARIABLE, "")
    if not api_key:
        raise WebsiteLookupError(f"No search API key. Set {API_KEY_VARIABLE} first.")
    search = _search_with_retry(search, pause)
    saved = load_saved(saved_path) if saved_path else {}
    results = []
    for org in organisations:
        entry = saved.get(_key(org))
        saved_url = entry.get("website") if isinstance(entry, dict) else None
        try:
            result = find_website(org, places, api_key, search, read, saved_url)
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            result = LookupResult(org, NOT_FOUND, 1)
        if result.outcome == FOUND:
            saved[_key(org)] = {
                "website": result.organisation.website,
                "confirmed_on": date.today().isoformat(),
            }
        results.append(result)
        if result.searches:
            pause(SEARCH_GAP_S)
    if saved_path and saved:
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.write_text(json.dumps(saved, indent=2, sort_keys=True) + "\n")
    return results
