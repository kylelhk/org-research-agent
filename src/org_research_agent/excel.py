"""Write research results to an Excel file for a person to review."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

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

HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
CHECK_FILL = PatternFill("solid", fgColor="FCE4D6")


def write_results(results: list[ResearchResult], path: Path | str) -> Path:
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

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path
