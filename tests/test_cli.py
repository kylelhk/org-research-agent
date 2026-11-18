"""Tests for the run command and the Excel output. Everything here is made up."""

import json

from openpyxl import load_workbook

from org_research_agent.claude_runner import ClaudeResult, ClaudeSignInError
from org_research_agent.cli import main
from org_research_agent.excel import COLUMNS, HEADER_ROW, STATUS_CHOICES
from org_research_agent.organisation import Organisation
from org_research_agent.suburbs import Place

SETTINGS = """
[area]
suburbs = ["Testville"]
radius_km = 3
min_organisations = 3
centre_lat = -1.5
centre_lon = 2.5

[fit]
types = ["dental practice"]
min_staff = 2

[prompts]
research = "Synthetic guidance."
"""

MANUAL = """
[[organisation]]
name = "Hand Added Dental"
website = "https://hand.test/"
"""

FACTS = {
    "read_status": "read",
    "couldnt_read_reason": "",
    "organisation_type": "dental practice",
    "suburb": "Testville",
    "general_contact": "info@clinic.test",
    "staff_count": 4,
    "staff_count_basis": "stated on site",
    "several_practitioners": False,
    "several_professions": False,
    "several_locations": False,
    "evidence_quote": "",
    "no_marketing_notice": False,
    "no_marketing_quote": "",
    "suspicious_instructions_seen": False,
    "source_urls": [],
}


def fake_find(lat, lon, radius_m):
    assert (lat, lon, radius_m) == (-1.5, 2.5, 3000)
    return [
        Organisation("Alpha Dental", "dental practice", website="https://alpha.test/"),
        Organisation("Beta Clinic", "clinic", website="https://beta.test/"),
    ]


def fake_runner(prompt, host, max_pages, fetch_log, **options):
    return ClaudeResult(text="", cost_usd=0.02, structured=FACTS)


def setup(tmp_path, settings=SETTINGS):
    (tmp_path / "settings.toml").write_text(settings)
    (tmp_path / "manual.toml").write_text(MANUAL)
    return [
        "--settings",
        str(tmp_path / "settings.toml"),
        "--manual",
        str(tmp_path / "manual.toml"),
        "--output-dir",
        str(tmp_path / "output"),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]


def run(tmp_path, *extra, settings=SETTINGS, runner=fake_runner):
    args = setup(tmp_path, settings) + list(extra)
    return main(args, runner=runner, find=fake_find, stamp="2026-11-08-0900")


def test_dry_run_lists_without_researching(tmp_path, capsys):
    def no_agent(*args, **kwargs):
        raise AssertionError("The agent should not run in a dry run.")

    assert run(tmp_path, "--dry-run", runner=no_agent) == 0
    output = capsys.readouterr().out
    assert (
        "3 organisations to research: 2 from the map, plus 1 from your hand-added list." in output
    )
    assert "- Hand Added Dental (unknown, https://hand.test/)" in output


def test_full_run_writes_spreadsheet(tmp_path, capsys):
    assert run(tmp_path) == 0
    path = tmp_path / "output" / "research-2026-11-08-0900.xlsx"
    sheet = load_workbook(path).active
    assert sheet["A1"].value == "Healthcare organisations: research list"
    assert [cell.value for cell in sheet[HEADER_ROW]] == [heading for heading, _, _ in COLUMNS]
    names = [
        sheet.cell(row=row, column=1).value for row in range(HEADER_ROW + 1, sheet.max_row + 1)
    ]
    assert names == ["Alpha Dental", "Beta Clinic", "Hand Added Dental"]
    row = {
        sheet.cell(row=HEADER_ROW, column=c).value: sheet.cell(row=HEADER_ROW + 1, column=c).value
        for c in range(1, 15)
    }
    assert row["Fit"] == "fit"
    assert not row["Evidence quote"]
    assert row["Status"] == "to review"
    output = capsys.readouterr().out
    assert "Results: 3 fit" in output
    assert "$0.06" in output


def test_status_column_has_a_dropdown(tmp_path):
    run(tmp_path)
    sheet = load_workbook(tmp_path / "output" / "research-2026-11-08-0900.xlsx").active
    rules = sheet.data_validations.dataValidation
    assert len(rules) == 1
    assert rules[0].formula1 == '"' + ",".join(STATUS_CHOICES) + '"'


def test_limit(tmp_path, capsys):
    assert run(tmp_path, "--limit", "1") == 0
    assert "1 organisations to research" in capsys.readouterr().out


def test_below_minimum_stops_unless_allowed(tmp_path, capsys):
    settings = SETTINGS.replace("min_organisations = 3", "min_organisations = 5")
    assert run(tmp_path, settings=settings) == 1
    assert "minimum is 5" in capsys.readouterr().err
    assert run(tmp_path, "--allow-fewer", "--dry-run", settings=settings) == 0


def test_no_map_uses_only_hand_added_list(tmp_path, capsys):
    assert run(tmp_path, "--no-map", "--allow-fewer", "--dry-run") == 0
    assert "1 organisations to research: 0 from the map, plus 1 from your hand-added list." in (
        capsys.readouterr().out
    )


def test_missing_centre_skips_the_map(tmp_path, capsys):
    settings = SETTINGS.replace("centre_lat = -1.5\ncentre_lon = 2.5\n", "")
    assert run(tmp_path, "--allow-fewer", "--dry-run", settings=settings) == 0
    assert "map search is skipped" in capsys.readouterr().out


def test_bad_settings_give_a_clear_error(tmp_path, capsys):
    assert run(tmp_path, settings="not = = toml") == 2
    assert "not valid TOML" in capsys.readouterr().err


def test_ctrl_c_saves_finished_organisations(tmp_path, capsys):
    calls = []

    def stops_on_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return fake_runner(*args, **kwargs)

    assert run(tmp_path, runner=stops_on_second) == 130
    sheet = load_workbook(tmp_path / "output" / "research-2026-11-08-0900.xlsx").active
    assert sheet.max_row == HEADER_ROW + 1
    assert "Stopped" in capsys.readouterr().out


def test_sign_in_failure_stops_the_run_at_once(tmp_path, capsys):
    calls = []

    def signed_out(*args, **kwargs):
        calls.append(1)
        raise ClaudeSignInError("Claude Code is not signed in.")

    assert run(tmp_path, runner=signed_out) == 1
    assert len(calls) == 1
    assert "not signed in" in capsys.readouterr().out
    assert not (tmp_path / "output" / "research-2026-11-08-0900.xlsx").exists()


def test_sign_in_failure_midway_saves_finished_organisations(tmp_path, capsys):
    calls = []

    def signs_out_on_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise ClaudeSignInError("Claude Code is not signed in.")
        return fake_runner(*args, **kwargs)

    assert run(tmp_path, runner=signs_out_on_second) == 130
    sheet = load_workbook(tmp_path / "output" / "research-2026-11-08-0900.xlsx").active
    assert sheet.max_row == HEADER_ROW + 1


def test_spreadsheet_holds_no_page_text_or_logs(tmp_path):
    run(tmp_path)
    sheet = load_workbook(tmp_path / "output" / "research-2026-11-08-0900.xlsx").active
    text = json.dumps([[cell.value for cell in row] for row in sheet.iter_rows()])
    assert "UNTRUSTED PAGE CONTENT" not in text


def test_map_search_is_retried_before_giving_up(tmp_path, capsys):
    calls = []

    def flaky_find(lat, lon, radius_m):
        calls.append(1)
        if len(calls) < 3:
            raise OSError("busy")
        return fake_find(lat, lon, radius_m)

    args = setup(tmp_path) + ["--dry-run"]
    assert main(args, find=flaky_find, pause=lambda s: None) == 0
    assert len(calls) == 3


def test_map_search_stops_after_five_failures(tmp_path, capsys):
    def broken_find(lat, lon, radius_m):
        raise OSError("down")

    args = setup(tmp_path) + ["--dry-run"]
    assert main(args, find=broken_find, pause=lambda s: None) == 1
    assert "failed 5 times (no answer)" in capsys.readouterr().err


def test_find_websites_fills_in_a_website_before_the_run(tmp_path, capsys):
    from org_research_agent.website_lookup import CHECKED, FOUND, LookupResult

    def fake_lookup(organisations, places, progress=None):
        assert "Testville" in places
        return [
            LookupResult(
                Organisation(o.name, o.type, o.suburb, "https://found.test/", o.source), FOUND, 1
            )
            if o.name == "Beta Clinic"
            else LookupResult(o, CHECKED)
            for o in organisations
        ]

    args = setup(tmp_path) + ["--find-websites", "--dry-run"]
    assert main(args, find=fake_find, lookup=fake_lookup) == 0
    output = capsys.readouterr().out
    assert "Website lookup: 1 found by search, 2 listed websites confirmed, 0 not found" in output
    assert "- Beta Clinic (clinic, https://found.test/, found by search)" in output


def test_find_websites_stops_without_a_key(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    args = setup(tmp_path) + ["--find-websites", "--dry-run"]
    assert main(args, find=fake_find) == 2
    assert "No search API key" in capsys.readouterr().err


def test_rows_without_a_local_website_say_what_the_search_found(tmp_path, capsys):
    from org_research_agent.website_lookup import CHECKED, NOT_FOUND, LookupResult

    def fake_lookup(organisations, places, progress=None):
        results = []
        for o in organisations:
            if o.name == "Alpha Dental":
                results.append(LookupResult(Organisation(o.name, o.type), NOT_FOUND, 1, True))
            elif o.name == "Beta Clinic":
                results.append(LookupResult(Organisation(o.name, o.type), NOT_FOUND, 1))
            else:
                results.append(LookupResult(o, CHECKED))
        return results

    args = setup(tmp_path) + ["--find-websites"]
    assert main(args, runner=fake_runner, find=fake_find, lookup=fake_lookup,
                stamp="2026-11-08-0900") == 0  # fmt: skip
    output = capsys.readouterr().out
    assert "2 not found, 1 of them with only a site for the wider business" in output
    sheet = load_workbook(tmp_path / "output" / "research-2026-11-08-0900.xlsx").active
    headings = [cell.value for cell in sheet[HEADER_ROW]]
    rows = {
        sheet.cell(row=r, column=1).value: dict(
            zip(headings, [c.value for c in sheet[r]], strict=True)
        )
        for r in range(HEADER_ROW + 1, sheet.max_row + 1)
    }
    alpha, beta = rows["Alpha Dental"], rows["Beta Clinic"]
    for row in (alpha, beta):
        assert row["Reason"] == "No website listed, and the search found none for this location."
    assert "chain's main site or another branch" in alpha["Notes"]
    assert not beta["Notes"]
    assert "chain" not in (rows["Hand Added Dental"]["Notes"] or "")


def test_spreadsheet_is_styled_for_reading(tmp_path):
    run(tmp_path)
    workbook = load_workbook(tmp_path / "output" / "research-2026-11-08-0900.xlsx")
    for sheet in workbook:
        assert sheet["A1"].value  # every tab has a title
        fonts = {c.font.name for row in sheet.iter_rows() for c in row if c.value is not None}
        assert fonts == {"Arial"}
    sheet = workbook["Research"]
    headings = {c.value: c for c in sheet[HEADER_ROW]}
    assert "couldn't read" in headings["Fit"].comment.text
    assert headings["Website"].comment is not None
    first = HEADER_ROW + 1
    assert sheet.cell(row=first, column=4).hyperlink.target == "https://alpha.test/"
    assert sheet.freeze_panes == f"B{first}"


def test_summary_counts_setup_time_and_leaves_out_rows_without_a_website(tmp_path, capsys):
    times = iter([100.0, 160.0])
    no_site = """
[[organisation]]
name = "No Site Dental"
"""
    args = setup(tmp_path)
    (tmp_path / "manual.toml").write_text(MANUAL + no_site)
    assert main(args, runner=fake_runner, find=fake_find, stamp="2026-11-08-0900",
                clock=lambda: next(times)) == 0  # fmt: skip
    output = capsys.readouterr().out
    assert "60s map search and website lookup" in output
    assert "(3 of 4 had a website)" in output


class PlaybackWindow:
    def __init__(self, answer):
        self.answer = answer
        self.closed = False

    def ask(self):
        return self.answer

    def warn(self, message):
        raise AssertionError(message)

    def confirm(self, message):
        raise AssertionError(message)

    def busy(self, busy):
        pass

    def close(self):
        self.closed = True


def run_with_window(tmp_path, answer, *extra, find=fake_find):
    window = PlaybackWindow(answer)
    args = setup(tmp_path) + ["--choose-suburbs", *extra]
    code = main(
        args,
        runner=fake_runner,
        find=find,
        stamp="2026-11-08-0900",
        window=lambda usual: window,
        locate=lambda name: Place("Otherton", (-3.0, 4.0)) if name == "Otherton" else None,
    )
    return code, window


def test_cancelling_the_suburb_window_researches_nothing(tmp_path, capsys):
    code, window = run_with_window(tmp_path, None)
    assert code == 3
    assert window.closed
    assert "Cancelled. Nothing was researched." in capsys.readouterr().out
    assert not (tmp_path / "output").exists()


def test_usual_suburbs_from_the_window_run_as_before(tmp_path, capsys):
    code, _ = run_with_window(tmp_path, (["Testville"], ""), "--dry-run")
    output = capsys.readouterr().out
    assert code == 0
    assert "Suburbs: Testville" in output
    assert (
        "3 organisations to research: 2 from the map, plus 1 from your hand-added list." in output
    )


def test_a_typed_suburb_gets_its_own_map_search(tmp_path, capsys):
    centres = []

    def find(lat, lon, radius_m):
        centres.append((lat, lon))
        if (lat, lon) == (-3.0, 4.0):
            return [Organisation("Gamma Physio", "physiotherapy", website="https://g.test/")]
        return fake_find(lat, lon, radius_m)

    code, _ = run_with_window(tmp_path, (["Testville"], "Otherton"), find=find)
    output = capsys.readouterr().out
    assert code == 0
    assert centres == [(-1.5, 2.5), (-3.0, 4.0)]
    assert "Suburbs: Testville, Otherton" in output
    sheet = load_workbook(tmp_path / "output" / "research-2026-11-08-0900.xlsx")["Research"]
    assert "Suburbs: Testville, Otherton." in sheet["A2"].value
    names = [sheet.cell(row, 1).value for row in range(HEADER_ROW + 1, sheet.max_row + 1)]
    assert "Gamma Physio" in names


def test_only_other_suburbs_leave_out_the_hand_added_list(tmp_path, capsys):
    def find(lat, lon, radius_m):
        return [Organisation("Gamma Physio", "physiotherapy", website="https://g.test/")]

    code, _ = run_with_window(tmp_path, ([], "Otherton"), "--dry-run", find=find)
    output = capsys.readouterr().out
    assert code == 0
    assert "hand-added list is for Testville, so it's left out" in output
    assert "fewer than the usual minimum of 3. The run continues." in output
    assert "Hand Added Dental" not in output


def test_suburbs_option_sets_the_run_without_a_window(tmp_path, capsys):
    args = setup(tmp_path) + ["--suburbs", "Nowhereville", "--dry-run"]
    code = main(args, runner=fake_runner, find=fake_find, locate=lambda name: None)
    output = capsys.readouterr().out
    assert code == 0
    assert "Nowhereville wasn't found in Perth" in output
    assert "None of these suburbs was found on the map" in output


def test_guidance_naming_the_usual_suburbs_gets_a_note_on_other_runs(tmp_path, capsys):
    settings = SETTINGS.replace("Synthetic guidance.", "Prefer practices near Testville.")
    args = setup(tmp_path, settings) + ["--suburbs", "Nowhereville", "--dry-run"]
    main(args, runner=fake_runner, find=fake_find, locate=lambda name: None)
    assert "the research guidance in the settings names Testville" in capsys.readouterr().out


def test_guidance_with_the_placeholder_gets_no_note(tmp_path, capsys):
    settings = SETTINGS.replace("Synthetic guidance.", "Prefer practices near {suburbs}.")
    args = setup(tmp_path, settings) + ["--suburbs", "Nowhereville", "--dry-run"]
    main(args, runner=fake_runner, find=fake_find, locate=lambda name: None)
    assert "research guidance" not in capsys.readouterr().out


def test_usual_run_gets_no_guidance_note(tmp_path, capsys):
    settings = SETTINGS.replace("Synthetic guidance.", "Prefer practices near Testville.")
    main(setup(tmp_path, settings) + ["--dry-run"], runner=fake_runner, find=fake_find)
    assert "research guidance" not in capsys.readouterr().out


def test_the_map_search_shows_each_suburb_and_retries(tmp_path, capsys):
    calls = []

    def flaky_find(lat, lon, radius_m):
        calls.append((lat, lon))
        if len(calls) == 1:
            raise OSError("busy")
        return fake_find(-1.5, 2.5, radius_m)

    args = setup(tmp_path) + ["--dry-run"]
    main(args, runner=fake_runner, find=flaky_find, pause=lambda seconds: None)
    output = capsys.readouterr().out
    assert "Map search around Testville ... no answer, trying again in 15 seconds" in output
    assert "2 found." in output


def test_the_count_line_counts_an_organisation_in_both_lists_once():
    from org_research_agent.cli import _count_line

    on_map = [Organisation("Alpha Dental", "dentist"), Organisation("Beta Clinic", "clinic")]
    manual = [Organisation("alpha dental", "dentist"), Organisation("Gamma Physio", "physio")]
    assert _count_line(3, on_map, manual) == (
        "3 organisations to research: 2 from the map, plus 1 from your hand-added "
        "list (1 more on it was already found on the map)."
    )
    assert _count_line(2, on_map, manual[:1]) == (
        "2 organisations to research: 2 from the map. The 1 on your hand-added list was among them."
    )
    assert _count_line(2, on_map, []) == "2 organisations to research: 2 from the map."


def test_overlapping_map_searches_say_how_many_are_different(tmp_path, capsys):
    places = {"bentley": Place("Bentley", (-3.0, 4.0))}
    args = setup(tmp_path) + ["--suburbs", "Testville,Bentley", "--dry-run"]
    main(
        args,
        runner=fake_runner,
        find=lambda lat, lon, radius_m: fake_find(-1.5, 2.5, radius_m),
        locate=lambda name: places.get(name.lower()),
        pause=lambda seconds: None,
    )
    output = capsys.readouterr().out
    assert "found 4 results. 2 names came up more than once, so there are 2 different" in output


def big_find(lat, lon, radius_m):
    return [Organisation(f"Clinic {n} {lat}", "clinic") for n in range(25)]


def test_a_large_run_from_the_window_asks_first_and_can_stop(tmp_path, capsys):
    places = {"bentley": Place("Bentley", (-3.0, 4.0))}
    window = PlaybackWindow((["Testville"], "Bentley"))
    questions = []
    code = main(
        setup(tmp_path) + ["--choose-suburbs"],
        runner=fake_runner,
        find=big_find,
        window=lambda usual: window,
        locate=lambda name: places.get(name.lower()),
        pause=lambda seconds: None,
        ask=lambda question: questions.append(question) or "",
    )
    assert code == 3
    assert "That's a large run: 51 organisations" in questions[0]
    assert "Stopped. Nothing was researched." in capsys.readouterr().out


def test_a_large_run_goes_ahead_after_yes(tmp_path, capsys):
    asked = []
    places = {"bentley": Place("Bentley", (-3.0, 4.0))}
    code = main(
        setup(tmp_path) + ["--choose-suburbs"],
        runner=fake_runner,
        find=big_find,
        window=lambda usual: PlaybackWindow((["Testville"], "Bentley")),
        locate=lambda name: places.get(name.lower()),
        pause=lambda seconds: None,
        ask=lambda question: asked.append(question) or "y",
    )
    assert code == 0
    assert asked
    assert "[51/51]" in capsys.readouterr().out


def test_a_busy_map_service_is_described_and_waits_double():
    import urllib.error

    from org_research_agent.cli import _map_problem

    busy = urllib.error.HTTPError("https://map.test/", 502, "Bad Gateway", {}, None)
    limited = urllib.error.HTTPError("https://map.test/", 429, "Too Many", {}, None)
    assert _map_problem(busy) == "the map service is busy"
    assert _map_problem(limited) == "too many searches just now"
    assert _map_problem(TimeoutError("timed out")) == "no answer in time"


def test_map_retries_wait_longer_each_time(tmp_path):
    waits = []

    def broken_find(lat, lon, radius_m):
        raise OSError("down")

    main(setup(tmp_path) + ["--dry-run"], find=broken_find, pause=waits.append)
    assert waits == [15, 30, 60, 120]


def test_a_map_entry_named_after_a_person_is_left_out(tmp_path, capsys):
    def find_with_person(lat, lon, radius_m):
        return [*fake_find(lat, lon, radius_m), Organisation("Dr A. B. Sample", "dentist")]

    main(setup(tmp_path) + ["--dry-run"], runner=fake_runner, find=find_with_person)
    output = capsys.readouterr().out
    assert "1 map entry named after a person left out" in output
    assert "Sample" not in output


def test_a_row_researched_on_a_chains_main_site_needs_a_manual_check(tmp_path, capsys):
    from org_research_agent.website_lookup import CHECKED, LookupResult

    def fake_lookup(organisations, places, progress=None):
        return [
            LookupResult(
                Organisation(o.name, o.type, o.suburb, "https://chain.test/", o.source),
                CHECKED, 1, True,
            )
            if o.name == "Alpha Dental"
            else LookupResult(o, CHECKED)
            for o in organisations
        ]  # fmt: skip

    args = setup(tmp_path) + ["--find-websites"]
    assert main(args, runner=fake_runner, find=fake_find, lookup=fake_lookup,
                stamp="2026-11-08-0900") == 0  # fmt: skip
    sheet = load_workbook(tmp_path / "output" / "research-2026-11-08-0900.xlsx").active
    headings = [cell.value for cell in sheet[HEADER_ROW]]
    rows = {
        sheet.cell(row=r, column=1).value: dict(
            zip(headings, [c.value for c in sheet[r]], strict=True)
        )
        for r in range(HEADER_ROW + 1, sheet.max_row + 1)
    }
    assert rows["Alpha Dental"]["Status"] == "needs manual check"
    assert "chain's main site" in rows["Alpha Dental"]["Notes"]


def test_the_list_opens_in_a_normal_sized_window(tmp_path):
    args = setup(tmp_path) + ["--no-map", "--allow-fewer"]
    assert main(args, runner=fake_runner, stamp="2026-11-08-0900") == 0
    view = load_workbook(tmp_path / "output" / "research-2026-11-08-0900.xlsx").views[0]
    assert (view.windowWidth, view.windowHeight) == (22000, 14000)
