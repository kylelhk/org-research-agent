"""Write research results to an Excel file for a person to review."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
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
    ("Signs of several staff", 30, lambda r: r.staff_signals),
    ("Fit", 12, lambda r: r.fit),
    ("Reason", 34, lambda r: r.fit_reason),
    ("Evidence quote", 50, lambda r: r.evidence),
    ("No-marketing flag", 30, lambda r: r.no_marketing),
    ("Source URLs", 45, lambda r: "\n".join(r.source_urls)),
    ("Checked on", 12, lambda r: r.checked_on),
    ("Status", 20, lambda r: r.status),
    ("Notes", 45, lambda r: "\n".join(r.notes)),
    ("Reviewer check time (min)", 16, lambda r: None),
]
REVIEW_TIME = "Reviewer check time (min)"

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

# Styling, matched to the handover guide: Arial, a navy header, light row banding.
FONT = "Arial"
NAVY, BLUE, INK, MUTED = "2D3D4F", "0094DC", "333F48", "6B7780"
RULE, BAND, TINT = "D5DCE2", "F7F9FB", "EEF6FB"
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
BAND_FILL = PatternFill("solid", fgColor=BAND)
CHECK_FILL = PatternFill("solid", fgColor="FCE4D6")  # needs manual check
INPUT_FILL = PatternFill("solid", fgColor="FFF8DC")  # cells for the reviewer to fill in
FIT_FILL = PatternFill("solid", fgColor="E2F0D9")
EDGE = Side(style="thin", color=RULE)
BORDER = Border(left=EDGE, right=EDGE, top=EDGE, bottom=EDGE)
TOP_LEFT = Alignment(wrap_text=True, vertical="top")

# The research table starts below a title, a subtitle, and a blank row.
HEADER_ROW = 4

# A note on each heading, shown when the reviewer hovers over it.
COLUMN_NOTES = {
    "Name": "The organisation's name, from OpenStreetMap or your hand-added list.",
    "Website": "The website the agent read. Blank if none was listed or found.",
    "Published general contact": "The phone number or email the website gives for the "
    "organisation. Never a person's own details.",
    "Stated staff size": 'A number the website states, such as "our team of eight". '
    "Never counted from names.",
    "Signs of several staff": 'Practitioners in the plural (such as "our dentists"), more '
    "than one profession, or more than one location.",
    "Fit": "fit: a type on your list with at least 2 staff stated, or signs of several staff.\n"
    "not a fit: the wrong type, or fewer than 2 staff stated.\n"
    "unknown: no staff number or sign found.\n"
    "couldn't read: no website, or the site couldn't be read.",
    "Reason": "Why the row got its Fit rating.",
    "Evidence quote": "A sentence copied word for word from the website and checked against "
    "the page. Names are shown as [name].",
    "No-marketing flag": "Whether the website says it doesn't want marketing messages. If "
    "yes, don't contact the organisation.",
    "Source URLs": "The pages the agent read for this row.",
    "Status": "Your review. Pick from the list as you check each row. Orange means "
    "the program wants you to look closely.",
    "Notes": "Anything the program removed, or wants you to check.",
    REVIEW_TIME: "Fill in: minutes you spent checking this row. The Run info tab picks "
    "it up from here.",
}
TIMING_NOTES = {
    "Agent time (s)": "Seconds the agent spent researching this organisation's website. The "
    "map search and website lookup at the start of the run are counted once, in the summary.",
    "Usage at list price ($)": "What the run would cost at Claude's list price. It counts "
    "against your Claude plan; you aren't billed for it.",
    "Reviewer check time (min)": "Taken from the last column of the Research tab. Fill it "
    "in there.",
    "Reviewer changed the rating? (Y/N)": "Fill in: Y if you changed the Fit rating, N if not.",
    "Reviewer rework time (min)": "Fill in: minutes spent fixing the row, if you changed it.",
    "Comments": "Fill in: anything worth noting about this row.",
    "Pages read": "Web pages the agent read for this organisation.",
    "Requests refused": "Pages the safeguards refused, such as staff profile pages.",
}
SUMMARY_NOTES = {
    "Organisations with a website researched": "Organisations with no website take no agent "
    "time, so they're left out of the average.",
    "Map search and website lookup (s)": "Time before the first website is read: the "
    "OpenStreetMap search and the Brave website lookup.",
    "Total agent time (s)": "The map search and website lookup, plus the time spent "
    "researching websites.",
    "Average agent time per organisation (s)": "Total agent time divided by the organisations "
    "with a website researched.",
    "Usage at list price ($)": "What the run would cost at Claude's list price. It counts "
    "against your Claude plan; you aren't billed for it.",
}
REVIEWER_COLUMNS = {
    "Reviewer changed the rating? (Y/N)",
    "Reviewer rework time (min)",
    "Comments",
}


def _font(**options) -> Font:
    return Font(name=FONT, size=options.pop("size", 10), color=options.pop("color", INK), **options)


def _note(text: str, lines: int = 4) -> Comment:
    note = Comment(text, "Research agent")
    note.width, note.height = 300, 22 * max(lines, text.count("\n") + 3)
    return note


def _title(sheet, title: str, subtitle: str) -> None:
    """A heading and a one-line explanation above the sheet's content."""
    sheet["A1"] = title
    sheet["A1"].font = _font(size=16, bold=True, color=NAVY)
    sheet["A2"] = subtitle
    sheet["A2"].font = _font(size=10, color=MUTED)
    sheet.row_dimensions[1].height = 28
    sheet.row_dimensions[2].height = 18


def _header(sheet, row: int, headings: list[str], notes: dict[str, str]) -> None:
    for column, heading in enumerate(headings, start=1):
        cell = sheet.cell(row=row, column=column, value=heading)
        cell.font = _font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = BORDER
        if heading in notes:
            cell.comment = _note(notes[heading])
    sheet.row_dimensions[row].height = 32


def _body_cell(cell, banded: bool) -> None:
    cell.font = _font()
    cell.alignment = TOP_LEFT
    cell.border = BORDER
    if banded:
        cell.fill = BAND_FILL


def write_results(
    results: list[ResearchResult],
    path: Path | str,
    run_label: str = "",
    setup_seconds: float = 0.0,
    suburbs: tuple[str, ...] | list[str] = (),
) -> Path:
    """Save results as a formatted spreadsheet and return its path."""
    path = Path(path)
    workbook = Workbook()
    workbook._named_styles["Normal"].font = Font(name=FONT, size=10)
    sheet = workbook.active
    sheet.title = "Research"
    headings = [heading for heading, _, _ in COLUMNS]
    run_text = f"Run {run_label}. " if run_label else ""
    if suburbs:
        run_text += f"Suburbs: {', '.join(suburbs)}. "
    _title(
        sheet,
        "Healthcare organisations: research list",
        f"{run_text}Review every row before you use the list. "
        "Hover over a heading to see what it means.",
    )
    _header(sheet, HEADER_ROW, headings, COLUMN_NOTES)

    column_of = {heading: index for index, heading in enumerate(headings, start=1)}
    for offset, result in enumerate(results):
        row = HEADER_ROW + 1 + offset
        for column, (_, _, value) in enumerate(COLUMNS, start=1):
            cell = sheet.cell(row=row, column=column, value=value(result))
            _body_cell(cell, banded=offset % 2 == 1)
        sheet.cell(row=row, column=column_of["Name"]).font = _font(bold=True)
        sheet.cell(row=row, column=column_of["Evidence quote"]).font = _font(italic=True)
        website = sheet.cell(row=row, column=column_of["Website"])
        if result.website:
            website.hyperlink = result.website
            website.font = _font(color=BLUE, underline="single")
        fit = sheet.cell(row=row, column=column_of["Fit"])
        if result.fit == "fit":
            fit.fill = FIT_FILL
            fit.font = _font(bold=True)
        elif result.fit == "couldn't read":
            fit.font = _font(color=MUTED)
        if result.status == "needs manual check":
            sheet.cell(row=row, column=column_of["Status"]).fill = CHECK_FILL
        sheet.cell(row=row, column=column_of[REVIEW_TIME]).fill = INPUT_FILL

    for index, (_, width, _) in enumerate(COLUMNS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    last_row = max(HEADER_ROW + len(results), HEADER_ROW + 1)
    sheet.freeze_panes = f"B{HEADER_ROW + 1}"
    sheet.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(len(COLUMNS))}{last_row}"
    _print_setup(sheet, HEADER_ROW)

    # A dropdown on the status column, so the reviewer picks from fixed choices.
    letter = get_column_letter(column_of["Status"])
    dropdown = DataValidation(
        type="list", formula1='"' + ",".join(STATUS_CHOICES) + '"', allow_blank=True
    )
    dropdown.add(f"{letter}{HEADER_ROW + 1}:{letter}{last_row + 200}")
    sheet.add_data_validation(dropdown)

    _write_run_info(workbook, results, run_label, setup_seconds, column_of[REVIEW_TIME])

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def _print_setup(sheet, header_row: int) -> None:
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = f"{header_row}:{header_row}"
    sheet.sheet_view.showGridLines = False


def _write_run_info(
    workbook: Workbook,
    results: list[ResearchResult],
    run_label: str,
    setup_seconds: float,
    review_column: int,
) -> None:
    sheet = workbook.create_sheet(RUN_INFO_SHEET)
    _title(
        sheet,
        "Run details and review timing",
        "The agent's time and usage for this run. Fill in the yellow columns as you review, "
        "to compare with the time it took by hand.",
    )
    count = len(results)
    with_website = sum(1 for r in results if r.website)
    research_seconds = sum(r.agent_seconds for r in results)
    # Rows 4 to 12. The total and the average are formulas, so they follow any edit.
    summary = [
        ("Run", run_label, None),
        ("Organisations on the list", count, "0"),
        ("Organisations with a website researched", with_website, "0"),
        ("Map search and website lookup (s)", round(setup_seconds, 1), "0.0"),
        ("Researching websites (s)", round(research_seconds, 1), "0.0"),
        ("Total agent time (s)", "=B7+B8", "0.0"),
        ("Average agent time per organisation (s)", "=IF(B6=0,0,B9/B6)", "0.0"),
        ("Usage at list price ($)", round(sum(r.cost_usd for r in results), 2), "$0.00"),
        ("Needs manual check", sum(r.status == "needs manual check" for r in results), "0"),
    ]
    row = 4
    for offset, (label, value, number_format) in enumerate(summary):
        label_cell = sheet.cell(row=row, column=1, value=label)
        value_cell = sheet.cell(row=row, column=2, value=value)
        for cell in (label_cell, value_cell):
            _body_cell(cell, banded=offset % 2 == 1)
        label_cell.font = _font(bold=True)
        value_cell.alignment = Alignment(horizontal="left", vertical="top")
        if number_format:
            value_cell.number_format = number_format
        if label in SUMMARY_NOTES:
            label_cell.comment = _note(SUMMARY_NOTES[label])
        row += 1

    heading_row = row + 1
    sheet.cell(row=heading_row, column=1, value="Each organisation").font = _font(
        size=12, bold=True, color=NAVY
    )
    header_row = heading_row + 1
    _header(sheet, header_row, TIMING_HEADINGS, TIMING_NOTES)
    for offset, result in enumerate(results):
        counts = result.fetch_counts
        values = [
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
        line = header_row + 1 + offset
        values[3] = _from_research(line, review_column)
        for column, (heading, value) in enumerate(zip(TIMING_HEADINGS, values, strict=True), 1):
            cell = sheet.cell(row=line, column=column, value=value)
            _body_cell(cell, banded=offset % 2 == 1)
            if heading in REVIEWER_COLUMNS:
                cell.fill = INPUT_FILL
        sheet.cell(row=line, column=4).number_format = "0.0"
        sheet.cell(row=line, column=1).font = _font(bold=True)
        sheet.cell(row=line, column=2).number_format = "0.0"
        sheet.cell(row=line, column=3).number_format = "$0.00"

    for column, width in zip("ABCDEFGHI", (40, 16, 18, 20, 22, 20, 40, 12, 44), strict=True):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = f"B{header_row + 1}"
    _print_setup(sheet, header_row)
    dropdown = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
    dropdown.add(f"E{header_row + 1}:E{header_row + count + 50}")
    sheet.add_data_validation(dropdown)


def _from_research(line: int, column: int) -> str:
    """A formula that looks up this row's organisation on the Research tab, by name.

    Matching by name keeps it right even if the Research tab is sorted or filtered.
    """
    source = f"Research!${get_column_letter(column)}:${get_column_letter(column)}"
    match = f"MATCH($A{line},Research!$A:$A,0)"
    value = f"INDEX({source},{match})"
    return f'=IFERROR(IF({value}="","",{value}),"")'
