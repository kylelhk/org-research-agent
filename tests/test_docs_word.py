"""Tests for turning Markdown into Word. All text is made up."""

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn

from org_research_agent.docs_word import convert, main

SAMPLE = """# A made-up document

Intro with **bold words** and `code` and a link https://example.test/page in full.

## First section
- [ ] An unticked box
- [x] A ticked box
- A plain bullet

1. First numbered line
2. Second numbered line

```bash
make-up-command --flag value
```

## Second section

| Item | Owner | Date |
|------|-------|------|
| One | Someone | |
| Two | Someone else | |

### A smaller heading
Closing text.
"""


def build(tmp_path, landscape=False):
    source = tmp_path / "doc.md"
    source.write_text(SAMPLE)
    return Document(str(convert(source, landscape=landscape)))


def paragraphs(document):
    return [(p.style.name, p.text) for p in document.paragraphs if p.text.strip()]


def test_headings_become_title_and_heading_levels(tmp_path):
    found = paragraphs(build(tmp_path))
    assert ("Title", "A made-up document") in found
    assert ("Heading 1", "First section") in found
    assert ("Heading 1", "Second section") in found
    assert ("Heading 2", "A smaller heading") in found


def test_checkboxes_are_real_box_characters(tmp_path):
    texts = [text for _, text in paragraphs(build(tmp_path))]
    assert "☐ An unticked box" in texts
    assert "☑ A ticked box" in texts
    assert not any(text.startswith("[ ]") or "- [" in text for text in texts)


def test_bullets_and_numbered_lines_stay_separate(tmp_path):
    found = paragraphs(build(tmp_path))
    assert ("List Bullet", "A plain bullet") in found
    texts = [text for _, text in found]
    assert "1. First numbered line" in texts
    assert "2. Second numbered line" in texts


def test_bold_and_code_are_formatted_and_markers_removed(tmp_path):
    document = build(tmp_path)
    intro = next(p for p in document.paragraphs if p.text.startswith("Intro"))
    assert "**" not in intro.text and "`" not in intro.text
    bold = [run.text for run in intro.runs if run.bold]
    assert bold == ["bold words"]
    assert any(run.font.name == "Courier New" and run.text == "code" for run in intro.runs)


def test_links_are_clickable_and_shown_in_full(tmp_path):
    document = build(tmp_path)
    links = [h for p in document.paragraphs for h in p.hyperlinks]
    assert [(link.text, link.address) for link in links] == [
        ("https://example.test/page", "https://example.test/page")
    ]


def test_code_fence_lines_are_kept_in_a_monospace_font(tmp_path):
    document = build(tmp_path)
    code = next(p for p in document.paragraphs if "make-up-command" in p.text)
    assert code.text == "make-up-command --flag value"
    assert code.runs[0].font.name == "Courier New"
    assert not any("```" in p.text for p in document.paragraphs)


def test_table_has_a_shaded_header_and_full_width(tmp_path):
    document = build(tmp_path)
    table = document.tables[0]
    assert [cell.text for cell in table.rows[0].cells] == ["Item", "Owner", "Date"]
    assert table.rows[1].cells[0].text == "One"
    shading = table.rows[0].cells[0]._tc.tcPr.find(qn("w:shd"))
    assert shading is not None
    grid = [int(g.get(qn("w:w"))) for g in table._tbl.tblGrid.findall(qn("w:gridCol"))]
    assert abs(sum(grid) - int(17.0 * 567)) < 20


def test_landscape_uses_a_wider_page_and_table(tmp_path):
    document = build(tmp_path, landscape=True)
    section = document.sections[0]
    assert section.orientation == WD_ORIENT.LANDSCAPE
    assert section.page_width > section.page_height
    grid = [int(g.get(qn("w:w"))) for g in document.tables[0]._tbl.tblGrid.findall(qn("w:gridCol"))]
    assert abs(sum(grid) - int(25.7 * 567)) < 20


def test_command_writes_a_docx_next_to_the_source(tmp_path, capsys):
    source = tmp_path / "doc.md"
    source.write_text(SAMPLE)
    assert main([str(source)]) == 0
    assert (tmp_path / "doc.docx").is_file()
    assert "Saved:" in capsys.readouterr().out


def test_command_reports_a_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "nope.md")]) == 1
    assert "not found" in capsys.readouterr().err


def test_no_markdown_marks_are_left_in_the_converted_documents():
    # The real documents for review must read cleanly in Word.
    from pathlib import Path

    for path in Path("docs").rglob("*.docx"):
        text = "\n".join(p.text for p in Document(str(path)).paragraphs)
        for table in Document(str(path)).tables:
            text += "\n".join(cell.text for row in table.rows for cell in row.cells)
        assert "**" not in text, path
        assert "```" not in text, path
        assert "- [ ]" not in text, path
