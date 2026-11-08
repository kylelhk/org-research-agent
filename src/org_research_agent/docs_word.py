"""Turn a Markdown document into a Word document for people to review, fill in, or sign.

Use it for anything a business owner, coordinator, or the consultant needs to read
and edit in Word. The Word file then becomes the working copy. It keeps headings,
bullets, numbered lines, checkboxes, tables, code lines, bold text, and links shown in
full. Wide tables suit landscape pages.

Usage:
    md-to-docx docs/handover/acceptance-record.md --landscape
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docx import Document

from org_research_agent.content_pack import (
    LANDSCAPE_TEXT_WIDTH_CM,
    TEXT_WIDTH_CM,
    _style,
    _write_markdown,
)


def convert(source: Path, output: Path | None = None, landscape: bool = False) -> Path:
    """Write a Word copy of a Markdown file and return its path."""
    document = Document()
    _style(document, landscape)
    width = LANDSCAPE_TEXT_WIDTH_CM if landscape else TEXT_WIDTH_CM
    # With top_level of -1, "#" is the title, "##" is Heading 1, and "###" is Heading 2.
    _write_markdown(document, source.read_text(), top_level=-1, width_cm=width)
    output = output or source.with_suffix(".docx")
    document.save(output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="md-to-docx", description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="The Markdown file.")
    parser.add_argument("--output", type=Path, help="Where to save the Word file.")
    parser.add_argument("--landscape", action="store_true", help="Use a landscape page.")
    args = parser.parse_args(argv)
    if not args.source.is_file():
        print(f"Error: {args.source} not found.", file=sys.stderr)
        return 1
    print(f"Saved: {convert(args.source, args.output, args.landscape)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
