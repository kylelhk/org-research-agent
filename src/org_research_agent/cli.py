"""Command line entry point: build the list, research each organisation, save to Excel.

Examples:
    org-research --dry-run           List the organisations without researching them.
    org-research --limit 3           Research the first 3 organisations only.
    org-research --no-map            Use only the hand-added list.
    org-research --find-websites     Find missing or broken websites first (needs BRAVE_API_KEY).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from org_research_agent.claude_runner import run_claude
from org_research_agent.excel import write_results
from org_research_agent.fetch_summary import (
    OTHER_WEBSITES,
    PAGE_CAP,
    PAGES_READ,
    PROFILE_PAGES,
    ROBOTS,
    TEAM_PAGES,
    describe_refusals,
    total,
)
from org_research_agent.manual import (
    DEFAULT_MANUAL_PATH,
    ManualListError,
    check_minimum,
    combine,
    load_manual,
)
from org_research_agent.organisation import Organisation
from org_research_agent.osm import find_organisations
from org_research_agent.research import DEFAULT_MAX_PAGES, STATUS_CHECK, research_organisation
from org_research_agent.settings import DEFAULT_SETTINGS_PATH, SettingsError, load_settings
from org_research_agent.website_lookup import (
    FOUND,
    NOT_FOUND,
    SAVED,
    WebsiteLookupError,
    find_websites,
)

MAP_ATTEMPTS = 3


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="org-research",
        description="Research local organisations and save the results to Excel.",
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--manual", default=str(DEFAULT_MANUAL_PATH))
    parser.add_argument("--no-map", action="store_true", help="Skip the OpenStreetMap search.")
    parser.add_argument("--limit", type=int, help="Research only the first N organisations.")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--dry-run", action="store_true", help="List organisations and stop.")
    parser.add_argument(
        "--allow-fewer", action="store_true", help="Run even below the minimum count."
    )
    parser.add_argument(
        "--find-websites",
        action="store_true",
        help="Search for missing or broken websites first. Needs BRAVE_API_KEY.",
    )
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--runs-dir", default="runs")
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    runner: Callable = run_claude,
    find: Callable[..., list[Organisation]] = find_organisations,
    stamp: str | None = None,
    lookup: Callable[..., list] = find_websites,
    pause: Callable[[float], None] = time.sleep,
) -> int:
    args = _parse_args(argv)

    try:
        settings = load_settings(args.settings)
        manual = load_manual(args.manual)
    except (SettingsError, ManualListError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    map_orgs: list[Organisation] = []
    area = settings.area
    if args.no_map:
        pass
    elif area.centre_lat is None or area.centre_lon is None:
        print("No centre point in the settings, so the map search is skipped.")
    else:
        # The public map service often fails once and then works, so try a few times.
        for attempt in range(1, MAP_ATTEMPTS + 1):
            try:
                map_orgs = find(area.centre_lat, area.centre_lon, int(area.radius_km * 1000))
                break
            except (OSError, ValueError) as error:
                if attempt == MAP_ATTEMPTS:
                    print(
                        f"Error: the map search failed {MAP_ATTEMPTS} times "
                        f"({type(error).__name__}). Wait a few minutes and try again.",
                        file=sys.stderr,
                    )
                    return 1
                pause(10 * attempt)

    organisations = combine(map_orgs, manual)
    if not args.allow_fewer:
        try:
            check_minimum(organisations, area.min_organisations)
        except ManualListError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
    if args.limit:
        organisations = organisations[: args.limit]

    print(
        f"{len(organisations)} organisations to research "
        f"({len(map_orgs)} from the map, {len(manual)} added by hand)."
    )
    found_by_search: set[str] = set()
    if args.find_websites:
        places = (*area.suburbs, *area.nearby_suburbs, *area.allowed_terms, "Perth")
        try:
            lookups = lookup(organisations, places)
        except WebsiteLookupError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 2
        organisations = [result.organisation for result in lookups]
        found_by_search = {r.organisation.name for r in lookups if r.outcome in {FOUND, SAVED}}
        outcomes = Counter(result.outcome for result in lookups)
        print(
            f"Website lookup: {outcomes[FOUND]} found by search, "
            f"{outcomes[SAVED]} saved from earlier searches, "
            f"{len(lookups) - outcomes[FOUND] - outcomes[SAVED] - outcomes[NOT_FOUND]} "
            f"listed websites confirmed, {outcomes[NOT_FOUND]} not found "
            f"({sum(r.searches for r in lookups)} searches)."
        )
    if args.dry_run:
        for org in organisations:
            note = ", found by search" if org.name in found_by_search else ""
            print(f"- {org.name} ({org.type}, {org.website or 'no website'}{note})")
        return 0

    stamp = stamp or datetime.now().strftime("%Y-%m-%d-%H%M")
    runs_dir = Path(args.runs_dir) / stamp
    output_path = Path(args.output_dir) / f"research-{stamp}.xlsx"
    results = []
    interrupted = False
    try:
        for number, org in enumerate(organisations, start=1):
            print(f"[{number}/{len(organisations)}] {org.name} ... ", end="", flush=True)
            result = research_organisation(
                org, settings, runs_dir, runner=runner, max_pages=args.max_pages
            )
            results.append(result)
            print(f"{result.fit} ({result.status}, {result.agent_seconds:.0f}s)")
    except KeyboardInterrupt:
        # Ctrl+C stops the run, but the organisations already done are still saved.
        interrupted = True
        print("\nStopped. Saving the organisations finished so far.")

    write_results(results, output_path, run_label=stamp)
    fits = Counter(result.fit for result in results)
    checks = sum(result.status == STATUS_CHECK for result in results)
    cost = sum(result.cost_usd for result in results)
    print()
    print("Results: " + ", ".join(f"{count} {fit}" for fit, count in sorted(fits.items())))
    print(f"Needs manual check: {checks}")
    seconds = sum(result.agent_seconds for result in results)
    if results:
        print(
            f"Agent time: {seconds:.0f}s in total, {seconds / len(results):.0f}s per organisation"
        )
    print(f"Usage at list price: ${cost:.2f} (counts against the Claude plan, not billed)")
    print(f"Saved: {output_path}")
    counts = total([result.fetch_counts for result in results])
    print(
        f"Pages read: {counts.get(PAGES_READ, 0)}. Requests refused: "
        f"{counts.get(OTHER_WEBSITES, 0)} other websites, {counts.get(PROFILE_PAGES, 0)} "
        f"staff profile pages, {counts.get(TEAM_PAGES, 0)} team pages, "
        f"{counts.get(ROBOTS, 0)} by robots.txt, "
        f"{counts.get(PAGE_CAP, 0)} over the page cap."
    )
    refused = [result.name for result in results if describe_refusals(result.fetch_counts)]
    if refused:
        print("Asked for something not allowed (see Notes): " + ", ".join(refused))
    print(f"Fetch log: {runs_dir / 'fetch-log.jsonl'}")
    return 130 if interrupted else 0
