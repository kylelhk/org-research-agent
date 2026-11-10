"""Build a Word review pack from a folder of Markdown drafts.

One pack per folder: each draft (guide, emails, invitation, slides) under its
own Heading 1, grouped by topic when there is more than one, then the source log
and review notes if present, then a sign-off table. After the pack is built, it
is the working copy: people edit it in Word with Track Changes, and content-check
reads it directly.

Usage:
    content-pack private/content/pack --title "All content" --draft 1
    content-pack private/content/pack --title "All content" --font Arial --logo logo.png
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_COLOR_INDEX
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from org_research_agent.content_check import kind_of

FONT = "Arial"
LINK_COLOUR = RGBColor(0x1F, 0x4E, 0x99)
HEADER_FILL = "DCE6F1"
TEXT_WIDTH_CM = 17.0
INLINE = re.compile(
    r"(?P<link>https://\S+)|(?P<placeholder>\[PLACEHOLDER[^\]]*\])"
    r"|(?P<tag>\{\{[^}]*\}\})|`(?P<code>[^`]+)`|\*\*(?P<bold>[^*]+)\*\*"
)
NUMBERED = re.compile(r"\d+[.)]\s+")
CHECKBOX = re.compile(r"[-*]\s+\[([ xX])\]\s+(.*)")
LANDSCAPE_TEXT_WIDTH_CM = 25.7
KIND_ORDER = {"guide": 0, "email": 1, "invitation": 2, "slides": 3}
HOW_TO_REVIEW = [
    "Turn on Track Changes (Review > Track Changes) before editing, so every change is visible.",
    "Use comments for questions. Highlighted text marks a placeholder for the business owner.",
    "Each fact is listed in the source log. Tick it once checked against the source.",
    "Before running content-check, accept or reject all tracked changes.",
]


def _topic(path: Path) -> str:
    """The topic in a guide or email's file name, such as "First home", or ""."""
    stem = path.stem.lower()
    match = re.search(r"-?(?:guide|email)", stem)
    if not match or kind_of(path).kind not in {"guide", "email"}:
        return ""
    words = stem[: match.start()].replace("-", " ").strip()
    return words[:1].upper() + words[1:]


def _heading_title(path: Path, with_topic: bool = False) -> str:
    kind = kind_of(path)
    if kind.kind == "email":
        title = f"Email {kind.number}"
    else:
        title = {"guide": "Guide", "invitation": "Invitation", "slides": "Presentation"}.get(
            kind.kind, path.stem
        )
    topic = _topic(path) if with_topic else ""
    return f"{topic}: {title}" if topic else title


def _brand(document: Document, font: str, table_fill: str | None) -> None:
    """Restyle a finished pack in a business's own font, with black headings."""
    styles = document.styles
    for name in ("Normal", "List Bullet", "Title", "Heading 1", "Heading 2", "Heading 3"):
        style = styles[name]
        style.font.name = font
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for attribute in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            fonts.set(qn(attribute), font)
        if name != "Normal" and name != "List Bullet":
            style.font.color.rgb = RGBColor(0, 0, 0)
            style.font.bold = True
    for name in ("Title", "Heading 1"):
        styles[name].font.all_caps = True
    # Most web fonts run wider and taller than Arial, so body text is set a little
    # smaller to keep a one-page guide on one page.
    styles["Normal"].font.size = Pt(10.5)
    # The default title has a coloured rule under it, which clashes with a plain style.
    title_format = styles["Title"].element.pPr
    if title_format is not None:
        for border in title_format.findall(qn("w:pBdr")):
            title_format.remove(border)
    if table_fill:
        for shading in document.element.body.iter(qn("w:shd")):
            shading.set(qn("w:fill"), table_fill)


def _add_logo(document: Document, logo: Path) -> None:
    """Put the business's logo at the top left of every page, inside the top margin."""
    if not logo.is_file():
        raise ValueError(f"Logo not found: {logo}")
    section = document.sections[0]
    section.header_distance = Cm(1)
    paragraph = section.header.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.add_run().add_picture(str(logo), height=Cm(0.6))


def _add_hyperlink(paragraph, url: str, size: Pt | None = None) -> None:
    """Add a clickable link whose visible text is the full address."""
    part = paragraph.part
    rel_id = part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rel_id)
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    colour = OxmlElement("w:color")
    colour.set(qn("w:val"), str(LINK_COLOUR))
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    props.append(colour)
    props.append(underline)
    if size:
        font_size = OxmlElement("w:sz")
        font_size.set(qn("w:val"), str(int(size.pt * 2)))
        props.append(font_size)
    run.append(props)
    text = OxmlElement("w:t")
    text.text = url
    text.set(qn("xml:space"), "preserve")
    run.append(text)
    link.append(run)
    paragraph._p.append(link)


def _add_inline(paragraph, text: str, bold: bool = False, size: Pt | None = None) -> None:
    """Add text, turning links, placeholders, tags, and code into formatted runs."""

    def add(value: str):
        run = paragraph.add_run(value)
        run.bold = bold
        if size:
            run.font.size = size
        return run

    position = 0
    for match in INLINE.finditer(text):
        if match.start() > position:
            add(text[position : match.start()])
        if match.group("link"):
            _add_hyperlink(paragraph, match.group("link"), size)
        elif match.group("placeholder"):
            run = add(match.group("placeholder"))
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            run.bold = True
        elif match.group("tag"):
            add(match.group("tag")).font.highlight_color = WD_COLOR_INDEX.GRAY_25
        elif match.group("bold"):
            add(match.group("bold")).bold = True
        else:
            add(match.group("code")).font.name = "Courier New"
        position = match.end()
    if position < len(text):
        add(text[position:])


def _blocks(markdown: str) -> list[tuple[str, str]]:
    """Split simple Markdown into (kind, text) blocks: heading levels, bullets,
    table rows, and paragraphs. Wrapped lines are joined back together."""
    blocks: list[tuple[str, str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(("p", " ".join(paragraph)))
            paragraph.clear()

    in_code = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            in_code = not in_code
        elif in_code:
            blocks.append(("code", line))
        elif not stripped:
            flush()
        elif stripped.startswith("|"):
            flush()
            blocks.append(("row", stripped))
        elif match := re.match(r"(#{1,3})\s+(.*)", stripped):
            flush()
            blocks.append((f"h{len(match.group(1))}", match.group(2)))
        elif box := CHECKBOX.match(stripped):
            flush()
            mark = "\u2611" if box.group(1) in "xX" else "\u2610"
            blocks.append(("check", f"{mark} {box.group(2)}"))
        elif re.match(r"[-*]\s+", stripped):
            flush()
            blocks.append(("bullet", stripped[2:].strip()))
        elif NUMBERED.match(stripped):
            flush()
            blocks.append(("number", stripped))
        elif line.startswith("  ") and blocks and blocks[-1][0] == "bullet" and not paragraph:
            kind, text = blocks.pop()
            blocks.append((kind, f"{text} {stripped}"))
        else:
            paragraph.append(stripped)
    flush()
    return blocks


def _table(document: Document, rows: list[str], width_cm: float = TEXT_WIDTH_CM) -> None:
    cells = [
        [cell.strip() for cell in row.strip("|").split("|")]
        for row in rows
        if not re.fullmatch(r"\|?[\s:|-]+\|?", row)
    ]
    if not cells:
        return
    columns = len(cells[0])
    table = document.add_table(rows=0, cols=columns)
    table.style = "Table Grid"
    table.autofit = False
    _set_borders(table)

    # Size columns by their longest entry (capped), so long links get the most room.
    weights = [
        min(max([len(row[i]) for row in cells if i < len(row)] + [4]), 45) for i in range(columns)
    ]
    widths = [Cm(width_cm * weight / sum(weights)) for weight in weights]

    for index, values in enumerate(cells):
        row = table.add_row().cells
        for column, (cell, value) in enumerate(zip(row, values, strict=False)):
            cell.width = widths[column]
            cell.paragraphs[0].text = ""
            _add_inline(cell.paragraphs[0], value, bold=index == 0, size=Pt(9))
            if index == 0:
                shading = OxmlElement("w:shd")
                shading.set(qn("w:val"), "clear")
                shading.set(qn("w:fill"), HEADER_FILL)
                cell._tc.get_or_add_tcPr().append(shading)
    # Set the grid and the total width too, so every viewer uses the same column sizes.
    for column, width in zip(table.columns, widths, strict=True):
        column.width = width
    table_width = OxmlElement("w:tblW")
    table_width.set(qn("w:type"), "dxa")
    table_width.set(qn("w:w"), str(int(Cm(width_cm).twips)))
    for existing in table._tbl.tblPr.findall(qn("w:tblW")):
        table._tbl.tblPr.remove(existing)
    table._tbl.tblPr.append(table_width)
    document.add_paragraph()


def _set_borders(table) -> None:
    """Give every cell a thin grey border, whatever the table style shows."""
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement(f"w:{edge}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:color"), "A6A6A6")
        borders.append(border)
    table._tbl.tblPr.append(borders)


def _hanging(paragraph, indent_cm: float = 0.7) -> None:
    """Indent a paragraph so wrapped lines line up under the first word."""
    paragraph.paragraph_format.left_indent = Cm(indent_cm)
    paragraph.paragraph_format.first_line_indent = Cm(-indent_cm)
    paragraph.paragraph_format.space_after = Pt(2)


def _write_markdown(
    document: Document, markdown: str, top_level: int, width_cm: float = TEXT_WIDTH_CM
) -> None:
    """Write Markdown blocks, with '#' headings one level below the section heading."""
    rows: list[str] = []
    for kind, text in _blocks(markdown):
        if kind == "row":
            rows.append(text)
            continue
        if rows:
            _table(document, rows, width_cm)
            rows = []
        if kind.startswith("h"):
            document.add_heading(text, level=max(min(top_level + int(kind[1]), 4), 0))
        elif kind == "bullet":
            _add_inline(document.add_paragraph(style="List Bullet"), text)
        elif kind in {"check", "number"}:
            paragraph = document.add_paragraph()
            _hanging(paragraph)
            _add_inline(paragraph, text)
        elif kind == "code":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.7)
            paragraph.paragraph_format.space_after = Pt(0)
            run = paragraph.add_run(text)
            run.font.name = "Courier New"
            run.font.size = Pt(9.5)
        elif text.lower().startswith("subject:"):
            paragraph = document.add_paragraph()
            paragraph.add_run("Subject: ").bold = True
            _add_inline(paragraph, text.split(":", 1)[1].strip(), bold=True)
        else:
            _add_inline(document.add_paragraph(), text)
    if rows:
        _table(document, rows, width_cm)


def _style(document: Document, landscape: bool = False) -> None:
    styles = document.styles
    styles["Normal"].font.name = FONT
    styles["Normal"].font.size = Pt(11)
    styles["Normal"].paragraph_format.space_after = Pt(6)
    styles["List Bullet"].paragraph_format.space_after = Pt(2)
    for name, size in (("Title", 22), ("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11)):
        styles[name].font.name = FONT
        styles[name].font.size = Pt(size)
    section = document.sections[0]
    section.page_height, section.page_width = Cm(29.7), Cm(21.0)
    if landscape:
        section.page_height, section.page_width = section.page_width, section.page_height
        section.orientation = WD_ORIENT.LANDSCAPE
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Cm(2))


def build_pack(
    folder: Path,
    title: str,
    draft: int,
    output: Path | None = None,
    font: str | None = None,
    table_fill: str | None = None,
    logo: Path | None = None,
) -> Path:
    """Build a review pack from the drafts, source log, and review notes in a folder.

    When the folder holds more than one topic, guides and emails are grouped by topic
    and their headings name it, such as "Investing: Email 2". A font restyles the pack
    to match a business's own style, and a logo goes at the top of every page.
    """
    candidates = [p for p in folder.glob("*.md") if kind_of(p).kind in KIND_ORDER]
    topics = sorted({_topic(p) for p in candidates} - {""})
    with_topic = len(topics) > 1
    drafts = sorted(
        candidates,
        key=lambda p: (
            KIND_ORDER[kind_of(p).kind] if KIND_ORDER[kind_of(p).kind] > 1 else 0,
            topics.index(_topic(p)) if with_topic and _topic(p) in topics else 0,
            KIND_ORDER[kind_of(p).kind],
            kind_of(p).number or 0,
        ),
    )
    if not drafts:
        raise ValueError(f"No drafts found in {folder}.")

    document = Document()
    _style(document)
    if logo:
        _add_logo(document, logo)
    document.add_heading(f"{title}: review pack", level=0)
    today = date.today()
    document.add_paragraph(f"Draft {draft}, built {today.day} {today:%B %Y}. For review.")
    document.add_heading("How to review this pack", level=1)
    for tip in HOW_TO_REVIEW:
        document.add_paragraph(tip, style="List Bullet")

    def new_page_heading(text: str) -> None:
        document.add_heading(text, level=1).paragraph_format.page_break_before = True

    for path in drafts:
        new_page_heading(_heading_title(path, with_topic))
        _write_markdown(document, path.read_text(), top_level=1)

    for name, heading in (("source-log.md", "Source log"), ("review-notes.md", "Review notes")):
        path = folder / name
        if path.is_file():
            new_page_heading(heading)
            text = re.sub(r"^#\s+.*\n", "", path.read_text(), count=1)
            _write_markdown(document, text, top_level=1)

    new_page_heading("Sign-off")
    rows = ["| Item | Consultant checked (date) | Business owner approved (date) | Notes |"]
    rows += [f"| {_heading_title(p, with_topic)} | | | |" for p in drafts]
    _table(document, rows)

    output = output or folder / f"{title} - review pack - draft {draft}.docx"
    if font:
        _brand(document, font, table_fill)
    document.save(output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="content-pack", description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="Folder holding the Markdown drafts.")
    parser.add_argument("--title", required=True, help='Topic name, such as "First home".')
    parser.add_argument("--draft", type=int, default=1, help="Draft number.")
    parser.add_argument("--output", type=Path, help="Where to save the pack.")
    parser.add_argument(
        "--font", help='A font to match the business\'s style, such as "Open Sans".'
    )
    parser.add_argument(
        "--table-fill", help="Table heading colour as six hex digits, such as D3D3D3."
    )
    parser.add_argument("--logo", type=Path, help="A logo image for the top of every page.")
    args = parser.parse_args(argv)
    try:
        path = build_pack(
            args.folder,
            args.title,
            args.draft,
            args.output,
            args.font,
            args.table_fill,
            args.logo,
        )
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
