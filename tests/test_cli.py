"""Tests for the run command and the Excel output. Everything here is made up."""

import json

from openpyxl import load_workbook

from org_research_agent.claude_runner import ClaudeResult, ClaudeSignInError
from org_research_agent.cli import main
from org_research_agent.excel import COLUMNS, HEADER_ROW, STATUS_CHOICES
from org_research_agent.organisation import Organisation

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
    assert "3 organisations to research (2 from the map, 1 added by hand)." in output
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
    assert "1 organisations to research (0 from the map, 1 added by hand)." in (
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


def test_map_search_stops_after_three_failures(tmp_path, capsys):
    def broken_find(lat, lon, radius_m):
        raise OSError("down")

    args = setup(tmp_path) + ["--dry-run"]
    assert main(args, find=broken_find, pause=lambda s: None) == 1
    assert "failed 3 times" in capsys.readouterr().err


def test_find_websites_fills_in_a_website_before_the_run(tmp_path, capsys):
    from org_research_agent.website_lookup import CHECKED, FOUND, LookupResult

    def fake_lookup(organisations, places):
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

    def fake_lookup(organisations, places):
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
