"""Checks that the Excel test record is complete and consistent, and that the public
files carry no individual client name."""

import re
import subprocess
import zipfile
from pathlib import Path

import pytest
from openpyxl import load_workbook

RECORD = Path("docs/test-evidence/test-record.xlsx")
SHOTS = Path("docs/test-evidence/screenshots")
STATUSES = {"Pass", "Partial", "Fail", "Not run"}
SHEETS = ["Read me", "Test plan", "Live runs", "Issues and retests", "Evidence"]

# The client's individual names are written in pieces, so this file does not contain them.
FORBIDDEN = [
    re.compile("dia" + "na", re.IGNORECASE),
    re.compile(r"\bg" + "oh" + r"\b", re.IGNORECASE),
]


@pytest.fixture(scope="module")
def workbook():
    return load_workbook(RECORD)


def rows(workbook, sheet):
    return list(workbook[sheet].iter_rows(min_row=2, values_only=True))


def test_record_has_the_expected_sheets(workbook):
    assert workbook.sheetnames == SHEETS


def test_every_test_has_a_valid_status_and_a_group(workbook):
    plan = rows(workbook, "Test plan")
    assert [row[0] for row in plan] == list(range(1, len(plan) + 1))
    assert {row[5] for row in plan} <= STATUSES
    assert all(row[1] and row[2] and row[3] and row[4] for row in plan)


def test_a_status_other_than_not_run_has_a_date_a_result_and_a_screenshot(workbook):
    for number, _, _, _, _, status, day, result, shots in rows(workbook, "Test plan"):
        if status != "Not run":
            assert day and result and shots, f"Test {number} has a status but no evidence"


def test_status_has_a_dropdown_and_colours(workbook):
    sheet = workbook["Test plan"]
    rules = [v.formula1 or "" for v in sheet.data_validations.dataValidation]
    assert any("Pass,Partial,Fail,Not run" in rule for rule in rules)
    assert len(sheet.conditional_formatting) >= 1


def test_every_screenshot_named_in_the_record_exists(workbook):
    named = set()
    for sheet in ("Test plan", "Live runs", "Issues and retests"):
        for row in rows(workbook, sheet):
            for cell in row:
                named.update(re.findall(r"[\w.-]+\.png", str(cell or "")))
    missing = sorted(name for name in named if not (SHOTS / name).is_file())
    assert not missing, missing


def test_every_screenshot_file_is_listed_in_the_evidence_sheet(workbook):
    listed = {row[0] for row in rows(workbook, "Evidence")}
    files = {p.name for p in SHOTS.glob("*.png")}
    assert files == listed


def test_evidence_links_point_into_the_screenshots_folder(workbook):
    for row in workbook["Evidence"].iter_rows(min_row=2, max_col=1):
        assert row[0].hyperlink.target == f"screenshots/{row[0].value}"


def test_commits_are_named_by_title_not_hash(workbook):
    # A hash would stop matching if history were ever rewritten.
    for sheet in ("Live runs", "Issues and retests", "Test plan"):
        for row in rows(workbook, sheet):
            for cell in row:
                assert not re.search(r"\(\b[0-9a-f]{7}\b\)|commit [0-9a-f]{7}\b", str(cell or ""))


def public_files():
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [Path(name) for name in listed if Path(name).is_file()]


def text_of(path):
    if path.suffix in {".docx", ".xlsx"}:
        with zipfile.ZipFile(path) as archive:
            return "\n".join(
                archive.read(name).decode("utf8", "ignore")
                for name in archive.namelist()
                if name.endswith((".xml", ".rels"))
            )
    if path.suffix in {".png", ".pyc"}:
        return ""
    return path.read_text(errors="ignore")


def test_no_individual_client_name_in_any_public_file():
    found = [
        str(path)
        for path in public_files()
        if any(pattern.search(text_of(path)) for pattern in FORBIDDEN)
    ]
    assert not found, found
