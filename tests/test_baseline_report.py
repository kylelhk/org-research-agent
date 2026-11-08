"""Tests for the timing sheet and the baseline report. All numbers are made up."""

import pytest
from openpyxl import load_workbook

from org_research_agent.baseline_report import build_report, main, read_rows
from org_research_agent.excel import RUN_INFO_SHEET, TIMING_HEADINGS, write_results
from org_research_agent.research import ResearchResult


def result(name, seconds=60.0, status="to review"):
    return ResearchResult(
        name=name,
        type="dental practice",
        suburb="Testville",
        website="https://x.test/",
        general_contact="unknown",
        staff_size="unknown",
        fit="unknown",
        fit_reason="",
        evidence="",
        no_marketing="no notice found",
        source_urls=[],
        checked_on="2026-11-08",
        status=status,
        cost_usd=0.02,
        agent_seconds=seconds,
    )


def make_workbook(tmp_path, reviewer):
    """Write a run, then fill in the reviewer columns: (check, changed, rework) per row."""
    path = write_results(
        [result("Alpha", 30), result("Beta", 90), result("Gamma", 60, "needs manual check")],
        tmp_path / "run.xlsx",
        run_label="2026-11-08-1000",
    )
    workbook = load_workbook(path)
    sheet = workbook[RUN_INFO_SHEET]
    header = next(r[0].row for r in sheet.iter_rows() if r[0].value == TIMING_HEADINGS[0])
    for offset, values in enumerate(reviewer, start=1):
        for column, value in zip("DEF", values, strict=True):
            if value is not None:
                sheet[f"{column}{header + offset}"] = value
    workbook.save(path)
    return path


def test_run_info_sheet_has_totals_and_a_table_for_the_reviewer(tmp_path):
    path = make_workbook(tmp_path, [])
    sheet = load_workbook(path)[RUN_INFO_SHEET]
    values = {row[0].value: row[1].value for row in sheet.iter_rows(max_row=6)}
    assert values["Run"] == "2026-11-08-1000"
    assert values["Organisations researched"] == 3
    assert values["Total agent time (s)"] == 180.0
    assert values["Average agent time per organisation (s)"] == 60.0
    assert values["Needs manual check"] == 1
    header = next(r for r in sheet.iter_rows() if r[0].value == "Organisation")
    assert [c.value for c in header[: len(TIMING_HEADINGS)]] == TIMING_HEADINGS


def test_research_sheet_is_unchanged(tmp_path):
    path = make_workbook(tmp_path, [])
    workbook = load_workbook(path)
    assert workbook.sheetnames == ["Research", RUN_INFO_SHEET]
    assert workbook["Research"]["A1"].value == "Name"


def test_report_adds_agent_check_and_rework_time(tmp_path):
    path = make_workbook(tmp_path, [(2, "N", 0), (3, "N", 1), (1, "Y", 4)])
    report = build_report(read_rows(path))
    assert report.reviewed == 3
    assert report.avg_agent_s == pytest.approx(60)
    assert report.avg_check_min == pytest.approx(2)
    assert report.avg_rework_min == pytest.approx(5 / 3)
    assert report.avg_total_min == pytest.approx(1 + 2 + 5 / 3)
    assert report.agreed == 2
    assert report.agreement_pct == pytest.approx(200 / 3)


def test_faster_than_baseline(tmp_path):
    path = make_workbook(tmp_path, [(2, "N", 0), (2, "N", 0), (2, "N", 0)])
    report = build_report(read_rows(path))
    assert report.avg_total_min == pytest.approx(3)
    assert report.faster_pct(20) == pytest.approx(85)
    assert report.faster_pct(6) == pytest.approx(50)


def test_averages_use_only_reviewed_rows(tmp_path):
    path = make_workbook(tmp_path, [(2, "N", 0), None_row(), None_row()])
    report = build_report(read_rows(path))
    assert (report.organisations, report.reviewed) == (3, 1)
    assert report.avg_agent_s == pytest.approx(30)


def None_row():  # noqa: N802
    return (None, None, None)


def test_empty_reviewer_columns_give_a_clear_error(tmp_path, capsys):
    path = make_workbook(tmp_path, [])
    assert main([str(path), "--baseline-min", "20"]) == 2
    assert "reviewer columns are empty" in capsys.readouterr().err


def test_command_passes_when_both_targets_are_met(tmp_path, capsys):
    path = make_workbook(tmp_path, [(2, "N", 0), (3, "N", 0), (2, "N", 1)])
    assert main([str(path), "--baseline-min", "20"]) == 0
    output = capsys.readouterr().out
    assert "PASS  " in output and "FAIL" not in output
    assert "estimate, not a measurement" in output
    assert "only 3 organisations reviewed" in output


def test_command_fails_when_agreement_is_low(tmp_path, capsys):
    path = make_workbook(tmp_path, [(2, "Y", 3), (2, "Y", 3), (2, "N", 0)])
    assert main([str(path), "--baseline-min", "20"]) == 1
    output = capsys.readouterr().out
    assert "FAIL  Reviewer agreed with 1 of 3 ratings, 33%" in output


def test_command_fails_when_not_fast_enough(tmp_path, capsys):
    path = make_workbook(tmp_path, [(10, "N", 5), (10, "N", 5), (10, "N", 5)])
    assert main([str(path), "--baseline-min", "20"]) == 1
    # One agent minute plus 10 to check and 5 to fix is 16 minutes, only 20% faster.
    assert "FAIL  20% faster than the baseline (target 60%)" in capsys.readouterr().out


def test_text_in_a_minutes_cell_is_reported(tmp_path, capsys):
    path = make_workbook(tmp_path, [("ten", "N", 0), (1, "N", 0), (1, "N", 0)])
    assert main([str(path), "--baseline-min", "20"]) == 2
    assert "not a number of minutes" in capsys.readouterr().err


def test_file_without_run_info_sheet(tmp_path, capsys):
    from openpyxl import Workbook

    path = tmp_path / "other.xlsx"
    Workbook().save(path)
    assert main([str(path), "--baseline-min", "20"]) == 2
    assert "No 'Run info' sheet" in capsys.readouterr().err
