"""Tests for the fetch log summary. All entries are made up."""

import json

import pytest
from openpyxl import load_workbook

from org_research_agent.claude_runner import ClaudeResult
from org_research_agent.cli import main
from org_research_agent.excel import RUN_INFO_SHEET, TIMING_HEADINGS, write_results
from org_research_agent.fetch_summary import (
    count_lines,
    describe_refusals,
    read_entries,
    summarise,
    total,
)
from org_research_agent.organisation import Organisation
from org_research_agent.research import research_organisation
from tests.test_cli import FACTS, setup
from tests.test_research import GOOD, FakeAgent, answer
from tests.test_research import SETTINGS as RESEARCH_SETTINGS


def entry(outcome, url="https://clinic.test/"):
    return {"time": "2026-11-08T10:00:00+00:00", "url": url, "outcome": outcome, "status": None}


def write_log(path, *entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as file:
        for item in entries:
            file.write(json.dumps(item) + "\n")


def test_outcomes_are_grouped():
    counts = summarise(
        [
            entry("fetched"),
            entry("fetched"),
            entry("blocked: off-site"),
            entry("blocked: off-site redirect"),
            entry("blocked: staff profile page"),
            entry("blocked: robots.txt"),
            entry("blocked: page cap"),
            entry("error: unreachable"),
            entry("error: http status"),
        ]
    )
    assert counts == {
        "pages_read": 2,
        "other_websites": 2,
        "profile_pages": 1,
        "robots": 1,
        "page_cap": 1,
        "errors": 2,
    }


def test_nothing_refused_gives_no_sentence():
    assert describe_refusals(summarise([entry("fetched"), entry("blocked: page cap")])) == ""


def test_sentence_names_each_kind_and_leaves_out_the_page_cap():
    counts = summarise(
        [
            entry("blocked: off-site"),
            entry("blocked: staff profile page"),
            entry("blocked: staff profile page"),
            entry("blocked: robots.txt"),
            entry("blocked: page cap"),
        ]
    )
    assert describe_refusals(counts) == (
        "refused by the safeguards: 1 request for another website, "
        "2 staff profile pages, 1 page blocked by robots.txt"
    )


def test_missing_log_means_nothing_happened(tmp_path):
    assert read_entries(tmp_path / "none.jsonl") == []
    assert count_lines(tmp_path / "none.jsonl") == 0


def test_only_lines_after_the_start_are_read(tmp_path):
    log = tmp_path / "log.jsonl"
    write_log(log, entry("fetched"), entry("fetched"))
    assert count_lines(log) == 2
    write_log(log, entry("blocked: off-site"))
    assert [e["outcome"] for e in read_entries(log, 2)] == ["blocked: off-site"]


def test_totals_add_up():
    assert total([{"pages_read": 2, "robots": 1}, {"pages_read": 3}]) == {
        "pages_read": 5,
        "robots": 1,
    }


class LoggingAgent(FakeAgent):
    """A fake agent that also writes lines to the fetch log, as the real tool does."""

    def __init__(self, *answers, log_entries=()):
        super().__init__(*answers)
        self.log_entries = list(log_entries)

    def __call__(self, prompt, host, max_pages, fetch_log, **options):
        write_log(fetch_log, *self.log_entries)
        return super().__call__(prompt, host, max_pages, fetch_log, **options)


ORG = Organisation("Testville Family Dental", "dentist", "unknown", "https://clinic.test/")


def research(agent, tmp_path):
    return research_organisation(ORG, RESEARCH_SETTINGS, tmp_path, runner=agent, today="2026-11-08")


def test_research_records_what_the_log_shows(tmp_path):
    agent = LoggingAgent(
        GOOD, log_entries=[entry("fetched"), entry("fetched"), entry("blocked: page cap")]
    )
    result = research(agent, tmp_path)
    assert result.fetch_counts == {"pages_read": 2, "page_cap": 1}
    assert not any("refused" in note for note in result.notes)


def test_refused_requests_are_noted_on_the_row(tmp_path):
    agent = LoggingAgent(
        GOOD,
        log_entries=[
            entry("fetched"),
            entry("blocked: off-site", "[off-site host: other.test]"),
            entry("blocked: staff profile page", "[redacted, may contain a name: clinic.test]"),
        ],
    )
    result = research(agent, tmp_path)
    assert (
        "refused by the safeguards: 1 request for another website, 1 staff profile page"
        in result.notes
    )


def test_each_organisation_only_counts_its_own_lines(tmp_path):
    first = research(LoggingAgent(GOOD, log_entries=[entry("blocked: off-site")]), tmp_path)
    second = research(LoggingAgent(GOOD, log_entries=[entry("fetched")]), tmp_path)
    assert first.fetch_counts == {"other_websites": 1}
    assert second.fetch_counts == {"pages_read": 1}
    assert not any("refused" in note for note in second.notes)


def test_a_retry_counts_both_attempts(tmp_path):
    bad = answer(evidence_quote="Dr Patel leads our team.")
    agent = LoggingAgent(bad, GOOD, log_entries=[entry("fetched")])
    result = research(agent, tmp_path)
    assert result.fetch_counts == {"pages_read": 2}


def test_run_info_sheet_has_pages_read_and_refused_columns(tmp_path):
    agent = LoggingAgent(GOOD, log_entries=[entry("fetched"), entry("blocked: robots.txt")])
    result = research(agent, tmp_path)
    path = write_results([result], tmp_path / "run.xlsx", run_label="demo")
    sheet = load_workbook(path)[RUN_INFO_SHEET]
    header = next(r for r in sheet.iter_rows() if r[0].value == "Organisation")
    assert [c.value for c in header[: len(TIMING_HEADINGS)]] == TIMING_HEADINGS
    assert TIMING_HEADINGS[-2:] == ["Pages read", "Requests refused"]
    row = sheet.cell(row=header[0].row + 1, column=1).row
    assert sheet.cell(row=row, column=8).value == 1
    assert sheet.cell(row=row, column=9).value == "1 page blocked by robots.txt"


@pytest.mark.parametrize("refused", [True, False])
def test_run_command_prints_totals_and_names_organisations(tmp_path, capsys, refused):
    def runner(prompt, host, max_pages, fetch_log, **options):
        extra = [entry("blocked: off-site")] if refused else []
        write_log(fetch_log, entry("fetched"), entry("fetched"), *extra)
        return ClaudeResult(text="", cost_usd=0.01, structured=FACTS)

    def find(lat, lon, radius_m):
        return [Organisation("Alpha Dental", "dental practice", website="https://alpha.test/")]

    args = setup(tmp_path) + ["--allow-fewer", "--no-map"]
    assert main(args, runner=runner, find=find, stamp="2026-11-08-0900") == 0
    output = capsys.readouterr().out
    assert "Pages read: 2." in output
    if refused:
        assert "1 other websites" in output
        assert "Asked for something not allowed (see Notes): Hand Added Dental" in output
    else:
        assert "0 other websites" in output
        assert "Asked for something not allowed" not in output
