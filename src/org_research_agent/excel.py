"""Write research results to an Excel file for a person to review."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from org_research_agent.fetch_summary import PAGES_READ, describe_refusals
from org_research_agent.research import ResearchResult

# Choices for the reviewer's status column.
STATUS_CHOICES = ("to review", "needs manual check", "approved", "not approved", "contacted")

# Column heading, width, and how to get the value from a result.
COLUMNS = [
    ("Name", 30, lambda r: r.name),
    ("Type", 18, lambda r: r.type),
    ("Suburb", 16, lambda r: r.suburb),
    ("Website", 30, lambda r: r.website),
    ("Published general contact", 26, lambda r: r.general_contact),
    ("Stated staff size", 22, lambda r: r.staff_size),
    ("Fit", 12, lambda r: r.fit),
    ("Reason", 34, lambda r: r.fit_reason),
    ("Evidence quote", 50, lambda r: r.evidence),
    ("No-marketing flag", 30, lambda r: r.no_marketing),
    ("Source URLs", 45, lambda r: "\n".join(r.source_urls)),
    ("Checked on", 12, lambda r: r.checked_on),
    ("Status", 20, lambda r: r.status),
    ("Notes", 45, lambda r: "\n".join(r.notes)),
]

# The Run info sheet records timing, and leaves columns for the reviewer's time, so
# every comparison with the baseline is made the same way.
RUN_INFO_SHEET = "Run info"
TIMING_HEADINGS = [
    "Organisation",
    "Agent time (s)",
    "Usage at list price ($)",
    "Reviewer check time (min)",
    "Reviewer changed the rating? (Y/N)",
    "Reviewer rework time (min)",
    "Comments",
    "Pages read",
    "Requests refused",
]

HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
CHECK_FILL = PatternFill("solid", fgColor="FCE4D6")


def write_results(results: list[ResearchResult], path: Path | str, run_label: str = "") -> Path:
    """Save results as a formatted spreadsheet and return its path."""
    path = Path(path)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Research"

    sheet.append([heading for heading, _, _ in COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    status_column = [heading for heading, _, _ in COLUMNS].index("Status") + 1
    for result in results:
        sheet.append([value(result) for _, _, value in COLUMNS])
        row = sheet.max_row
        for cell in sheet[row]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        if result.status == "needs manual check":
            sheet.cell(row=row, column=status_column).fill = CHECK_FILL

    for index, (_, width, _) in enumerate(COLUMNS, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = sheet.dimensions

    # A dropdown on the status column, so the reviewer picks from fixed choices.
    letter = sheet.cell(row=1, column=status_column).column_letter
    dropdown = DataValidation(
        type="list", formula1='"' + ",".join(STATUS_CHOICES) + '"', allow_blank=True
    )
    dropdown.add(f"{letter}2:{letter}{max(sheet.max_row, 2) + 200}")
    sheet.add_data_validation(dropdown)

    _write_run_info(workbook, results, run_label)

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def _write_run_info(workbook: Workbook, results: list[ResearchResult], run_label: str) -> None:
    sheet = workbook.create_sheet(RUN_INFO_SHEET)
    total_seconds = sum(r.agent_seconds for r in results)
    count = len(results)
    summary = [
        ("Run", run_label),
        ("Organisations researched", count),
        ("Total agent time (s)", round(total_seconds, 1)),
        (
            "Average agent time per organisation (s)",
            round(total_seconds / count, 1) if count else 0,
        ),
        ("Usage at list price ($)", round(sum(r.cost_usd for r in results), 2)),
        ("Needs manual check", sum(r.status == "needs manual check" for r in results)),
    ]
    for label, value in summary:
        sheet.append([label, value])
        sheet.cell(row=sheet.max_row, column=1).font = Font(bold=True)

    sheet.append([])
    sheet.append(TIMING_HEADINGS)
    header_row = sheet.max_row
    for cell in sheet[header_row]:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for result in results:
        counts = result.fetch_counts
        sheet.append(
            [
                result.name,
                round(result.agent_seconds, 1),
                round(result.cost_usd, 2),
                None,
                None,
                None,
                None,
                counts.get(PAGES_READ, 0),
                describe_refusals(counts).removeprefix("refused by the safeguards: "),
            ]
        )

    for column, width in zip("ABCDEFGHI", (40, 16, 18, 20, 22, 20, 40, 12, 44), strict=True):
        sheet.column_dimensions[column].width = width
    dropdown = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
    dropdown.add(f"E{header_row + 1}:E{header_row + count + 50}")
    sheet.add_data_validation(dropdown)
