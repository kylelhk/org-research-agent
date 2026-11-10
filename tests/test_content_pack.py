"""Tests for Word review packs: building them, and checking them. All text is made up."""

import base64

import pytest
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from org_research_agent.content_check import FAIL, check_paths, main, read_pack
from org_research_agent.content_pack import _add_hyperlink, build_pack
from tests.test_content_check import DISCLAIMER, GOOD_EMAIL_1, GOOD_GUIDE, GOOD_INVITATION

SOURCE_LOG = """# Source log

| # | Claim | Source |
|---|-------|--------|
| 1 | A made-up claim | https://example.test/source |
"""

BAD_EMAIL_2 = f"""Subject: Week 2

Hi {{{{ contact.FIRSTNAME | default: "there" }}}},

Approval is guaranteed, so act now.
Sent by [PLACEHOLDER SENDER DETAILS].

{DISCLAIMER}

Unsubscribe: {{{{ unsubscribe }}}}
"""


def make_drafts(folder, email_2=BAD_EMAIL_2):
    folder.mkdir(exist_ok=True)
    (folder / "first-home-guide.md").write_text(GOOD_GUIDE)
    (folder / "first-home-email-1.md").write_text(GOOD_EMAIL_1)
    (folder / "first-home-email-2.md").write_text(email_2)
    (folder / "lunch-and-learn-invitation.md").write_text(GOOD_INVITATION)
    (folder / "source-log.md").write_text(SOURCE_LOG)
    return folder


def headings(path):
    return [p.text for p in Document(str(path)).paragraphs if p.style.name == "Heading 1"]


def test_pack_has_one_section_per_draft_in_order(tmp_path):
    pack = build_pack(make_drafts(tmp_path / "drafts"), "First home", 1)
    assert pack.name == "First home - review pack - draft 1.docx"
    assert headings(pack) == [
        "How to review this pack",
        "Guide",
        "Email 1",
        "Email 2",
        "Invitation",
        "Source log",
        "Sign-off",
    ]


def test_links_are_clickable_and_show_the_full_address(tmp_path):
    pack = build_pack(make_drafts(tmp_path / "drafts"), "First home", 1)
    links = [h for p in Document(str(pack)).paragraphs for h in p.hyperlinks]
    assert links
    assert all(link.text == link.address for link in links)


def test_placeholders_are_highlighted(tmp_path):
    pack = build_pack(make_drafts(tmp_path / "drafts"), "First home", 1)
    runs = [r for p in Document(str(pack)).paragraphs for r in p.runs]
    placeholder = [r for r in runs if r.text.startswith("[PLACEHOLDER")]
    assert placeholder and placeholder[0].font.highlight_color == WD_COLOR_INDEX.YELLOW


def test_source_log_becomes_a_table(tmp_path):
    pack = build_pack(make_drafts(tmp_path / "drafts"), "First home", 1)
    tables = Document(str(pack)).tables
    log = tables[0]
    assert [c.text for c in log.rows[0].cells] == ["#", "Claim", "Source"]
    assert log.rows[1].cells[1].text == "A made-up claim"


def test_pack_gives_the_same_results_as_the_markdown(tmp_path):
    # The checker must judge a draft the same way, whether it is Markdown or in a pack.
    folder = make_drafts(tmp_path / "drafts")
    pack = build_pack(folder, "First home", 1, output=tmp_path / "pack.docx")

    def summary(results):
        return sorted(
            (r.kind.kind, r.kind.number, f.level, f.section, f.message)
            for r in results
            for f in r.findings
        )

    assert summary(check_paths([folder])) == summary(check_paths([pack]))
    assert any(level == FAIL for *_, level, _, _ in summary(check_paths([pack])))


def test_pack_findings_point_to_paragraphs(tmp_path):
    pack = build_pack(make_drafts(tmp_path / "drafts"), "First home", 1)
    email_2 = next(r for r in check_paths([pack]) if r.label.endswith("> Email 2"))
    promised = next(f for f in email_2.findings if "Promised" in f.message)
    assert email_2.unit == "paragraph"
    assert promised.line == 3  # Subject, greeting, then this paragraph.


def test_notes_and_sign_off_sections_are_not_checked(tmp_path):
    pack = build_pack(make_drafts(tmp_path / "drafts"), "First home", 1)
    labels = [r.label for r in check_paths([pack])]
    assert not any(
        label.endswith(("Source log", "Sign-off", "How to review this pack")) for label in labels
    )


def test_hidden_link_text_in_word_is_caught(tmp_path):
    document = Document()
    document.add_heading("Guide", level=1)
    paragraph = document.add_paragraph("Read the guide ")
    _add_hyperlink(paragraph, "https://example.test/guide")
    paragraph._p.findall(".//" + qn("w:t"))[-1].text = "here"
    document.add_paragraph(DISCLAIMER)
    path = tmp_path / "pack.docx"
    document.save(str(path))
    findings = check_paths([path])[0].findings
    assert any(f.level == FAIL and "Hidden link text" in f.message for f in findings)


def test_tracked_changes_must_be_accepted_first(tmp_path):
    pack = build_pack(make_drafts(tmp_path / "drafts"), "First home", 1)
    document = Document(str(pack))
    insertion = OxmlElement("w:ins")
    insertion.set(qn("w:id"), "1")
    insertion.set(qn("w:author"), "Reviewer")
    document.paragraphs[-1]._p.append(insertion)
    document.save(str(pack))
    _, tracked = read_pack(pack)
    assert tracked
    results = check_paths([pack])
    assert len(results) == 1
    assert "Tracked changes found" in results[0].findings[0].message


def test_word_lock_files_are_skipped(tmp_path, capsys):
    folder = make_drafts(tmp_path / "drafts", email_2=GOOD_EMAIL_1.replace("1", "2"))
    build_pack(folder, "First home", 1)
    (folder / "~$First home - review pack - draft 1.docx").write_bytes(b"lock")
    for path in folder.glob("*.md"):
        path.unlink()
    assert main([str(folder)]) == 0
    assert "~$" not in capsys.readouterr().out


def test_content_pack_command(tmp_path, capsys):
    from org_research_agent.content_pack import main as pack_main

    folder = make_drafts(tmp_path / "drafts")
    assert pack_main([str(folder), "--title", "First home", "--draft", "2"]) == 0
    assert (folder / "First home - review pack - draft 2.docx").is_file()
    assert pack_main([str(tmp_path), "--title", "Empty"]) == 1


def test_two_topics_are_grouped_and_named(tmp_path):
    folder = make_drafts(tmp_path / "drafts")
    (folder / "investing-guide.md").write_text(GOOD_GUIDE)
    (folder / "investing-email-1.md").write_text(GOOD_EMAIL_1)
    pack = build_pack(folder, "All content", 1)
    assert headings(pack) == [
        "How to review this pack",
        "First home: Guide",
        "First home: Email 1",
        "First home: Email 2",
        "Investing: Guide",
        "Investing: Email 1",
        "Invitation",
        "Source log",
        "Sign-off",
    ]
    # The checker still recognises each draft from its heading.
    labels = [result.label.split(" > ")[1] for result in check_paths([pack], DISCLAIMER)]
    assert labels == headings(pack)[1:7]


def test_pack_can_use_the_business_font(tmp_path):
    folder = make_drafts(tmp_path / "drafts")
    pack = build_pack(folder, "First home", 1, font="Open Sans", table_fill="D3D3D3")
    document = Document(str(pack))
    for name in ("Normal", "Heading 1", "Title"):
        assert document.styles[name].font.name == "Open Sans"
    assert document.styles["Heading 1"].font.all_caps
    assert str(document.styles["Heading 1"].font.color.rgb) == "000000"
    fills = {s.get(qn("w:fill")) for s in document.element.body.iter(qn("w:shd"))}
    assert fills == {"D3D3D3"}


# A 1 x 1 pixel PNG, enough for Word to place an image.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_pack_puts_the_logo_at_the_top_of_every_page(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(TINY_PNG)
    pack = build_pack(make_drafts(tmp_path / "drafts"), "First home", 1, logo=logo)
    header = Document(str(pack)).sections[0].header
    assert not header.is_linked_to_previous
    assert header.part.element.findall(".//" + qn("w:drawing"))


def test_a_missing_logo_is_reported(tmp_path):
    with pytest.raises(ValueError, match="Logo not found"):
        build_pack(make_drafts(tmp_path / "drafts"), "First home", 1, logo=tmp_path / "no.png")
