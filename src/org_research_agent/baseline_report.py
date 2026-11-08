"""Compare a run with the baseline, using the "Run info" sheet of its Excel file.

The sheet holds the agent's time for each organisation. The reviewer adds how long
checking took, whether they changed the rating, and how long fixing took. This command
adds those up the same way every time and compares the result with the baseline.

The baseline is the business owner's estimate, not a measurement, and it is passed on
the command line so no client figures are stored in this repository:

    baseline-report output/research-2026-11-14-1030.xlsx --baseline-min 20
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from org_research_agent.excel import RUN_INFO_SHEET, TIMING_HEADINGS

DEFAULT_TARGET_FASTER_PCT = 60.0
DEFAULT_TARGET_AGREEMENT_PCT = 80.0


@dataclass(frozen=True)
class Row:
    name: str
    agent_seconds: float
    check_min: float | None
    changed: str | None
    rework_min: float | None


@dataclass(frozen=True)
class Report:
    organisations: int
    reviewed: int
    avg_agent_s: float
    avg_check_min: float
    avg_rework_min: float
    avg_total_min: float
    agreed: int

    @property
    def agreement_pct(self) -> float:
        return 100 * self.agreed / self.reviewed if self.reviewed else 0.0

    def faster_pct(self, baseline_min: float) -> float:
        return 100 * (1 - self.avg_total_min / baseline_min)


def _number(value) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"'{value}' is not a number of minutes.") from error


def read_rows(path: Path) -> list[Row]:
    workbook = load_workbook(path)
    if RUN_INFO_SHEET not in workbook.sheetnames:
        raise ValueError(f"No '{RUN_INFO_SHEET}' sheet in this file.")
    sheet = workbook[RUN_INFO_SHEET]
    header_row = next(
        (row[0].row for row in sheet.iter_rows() if row[0].value == TIMING_HEADINGS[0]), None
    )
    if header_row is None:
        raise ValueError("The Run info sheet has no organisation table.")
    rows = []
    for values in sheet.iter_rows(min_row=header_row + 1, values_only=True):
        if not values[0]:
            continue
        padded = list(values) + [None] * (len(TIMING_HEADINGS) - len(values))
        changed = str(padded[4]).strip().upper()[:1] if padded[4] else None
        rows.append(
            Row(
                name=str(padded[0]),
                agent_seconds=float(padded[1] or 0),
                check_min=_number(padded[3]),
                changed=changed,
                rework_min=_number(padded[5]),
            )
        )
    return rows


def build_report(rows: list[Row]) -> Report:
    """Average the times over the organisations the reviewer has filled in."""
    reviewed_rows = [row for row in rows if row.check_min is not None]
    if not reviewed_rows:
        raise ValueError("The reviewer columns are empty, so there is nothing to compare yet.")
    count = len(reviewed_rows)
    avg_agent = sum(r.agent_seconds for r in reviewed_rows) / count
    avg_check = sum(r.check_min or 0 for r in reviewed_rows) / count
    avg_rework = sum(r.rework_min or 0 for r in reviewed_rows) / count
    return Report(
        organisations=len(rows),
        reviewed=count,
        avg_agent_s=avg_agent,
        avg_check_min=avg_check,
        avg_rework_min=avg_rework,
        avg_total_min=avg_agent / 60 + avg_check + avg_rework,
        agreed=sum(1 for r in reviewed_rows if r.changed != "Y"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="baseline-report", description=__doc__.splitlines()[0])
    parser.add_argument("excel", type=Path, help="The run's Excel file.")
    parser.add_argument(
        "--baseline-min", type=float, required=True, help="Baseline minutes per organisation."
    )
    parser.add_argument("--target-faster", type=float, default=DEFAULT_TARGET_FASTER_PCT)
    parser.add_argument("--target-agreement", type=float, default=DEFAULT_TARGET_AGREEMENT_PCT)
    args = parser.parse_args(argv)

    try:
        report = build_report(read_rows(args.excel))
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    faster = report.faster_pct(args.baseline_min)
    print(f"File: {args.excel}")
    print(
        f"Organisations: {report.organisations}, reviewed: {report.reviewed} "
        "(averages use the reviewed ones)\n"
    )
    print("Time per organisation, in minutes")
    print(f"  Agent run time      {report.avg_agent_s / 60:6.1f}  ({report.avg_agent_s:.0f}s)")
    print(f"  Reviewer checking   {report.avg_check_min:6.1f}")
    print(f"  Reviewer rework     {report.avg_rework_min:6.1f}")
    print(f"  Total               {report.avg_total_min:6.1f}")
    print(f"  Baseline (estimate) {args.baseline_min:6.1f}\n")

    ok_speed = faster >= args.target_faster
    ok_agree = report.agreement_pct >= args.target_agreement
    print(
        f"{'PASS' if ok_speed else 'FAIL'}  {faster:.0f}% faster than the baseline "
        f"(target {args.target_faster:.0f}%)"
    )
    print(
        f"{'PASS' if ok_agree else 'FAIL'}  Reviewer agreed with {report.agreed} of "
        f"{report.reviewed} ratings, {report.agreement_pct:.0f}% "
        f"(target {args.target_agreement:.0f}%)\n"
    )
    print("The baseline is the owner's estimate, not a measurement. Report the two apart.")
    if report.reviewed < 10:
        print(f"Note: only {report.reviewed} organisations reviewed. The brief asks for about 10.")
    return 0 if ok_speed and ok_agree else 1


if __name__ == "__main__":
    sys.exit(main())
