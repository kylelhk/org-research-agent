"""Tests for the run command and the Excel output. Everything here is made up."""

import json

from openpyxl import load_workbook

from org_research_agent.claude_runner import ClaudeResult
from org_research_agent.cli import main
from org_research_agent.excel import COLUMNS, STATUS_CHOICES
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
    assert [cell.value for cell in sheet[1]] == [heading for heading, _, _ in COLUMNS]
    names = [sheet.cell(row=row, column=1).value for row in range(2, sheet.max_row + 1)]
    assert names == ["Alpha Dental", "Beta Clinic", "Hand Added Dental"]
    row = {
        sheet.cell(row=1, column=c).value: sheet.cell(row=2, column=c).value for c in range(1, 15)
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
    assert sheet.max_row == 2
    assert "Stopped" in capsys.readouterr().out


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
    assert (
        "Website lookup: 1 found by search, 0 saved from earlier searches, "
        "2 listed websites confirmed, 0 not found" in output
    )
    assert "- Beta Clinic (clinic, https://found.test/, found by search)" in output


def test_find_websites_stops_without_a_key(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    args = setup(tmp_path) + ["--find-websites", "--dry-run"]
    assert main(args, find=fake_find) == 2
    assert "No search API key" in capsys.readouterr().err
