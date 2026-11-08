"""Tests for the content checker. All sample text is made up for testing."""

from pathlib import Path

import pytest

from org_research_agent.content_check import (
    CHECK,
    FAIL,
    check_draft,
    kind_of,
    main,
    reading_grade,
)

DISCLAIMER = "Disclaimer: This is general information only and is not financial advice."

GOOD_GUIDE = f"""# Buying your first home: the steps

Buying a first home has a few stages. This guide explains them in plain words.

## 1. Work out your budget
Lenders look at your income, your expenses, and any debts. Many people start by
listing their regular costs.

## 2. Save a deposit
A deposit is the part of the price you pay yourself. The amount lenders ask for
varies, so it is worth asking a broker what applies to you.

## 3. Check government schemes
Some schemes help first home buyers. Rules change, so check the official website
for the current details.

## 4. Talk to a broker
A broker can explain your options and compare lenders for you.

{DISCLAIMER}
"""

GOOD_EMAIL_1 = f"""Subject: Your first home guide is here

Thanks for signing up. Here is the guide you asked for:
https://example.test/first-home-guide

Over the next few weeks we will send three more short emails, one a week.

{DISCLAIMER}

Unsubscribe: https://example.test/unsubscribe
"""

GOOD_INVITATION = f"""Subject: A free lunch-and-learn for your team

Hello,

I am a local mortgage broker. I run free 15-minute lunch-and-learn sessions for
workplace teams about buying a first home and investing for the first time.

If you would prefer not to hear from me again, just reply and let me know.

{DISCLAIMER}
"""

GOOD_COMPLEX_EMAIL = f"""Subject: Trusts and companies: the basics

Some people buy property through a trust or a company. Each structure has
different costs and rules, so you should speak to an accountant or licensed
adviser before deciding.

{DISCLAIMER}

Unsubscribe: https://example.test/unsubscribe
"""


def check(text, name):
    return check_draft(text, Path(name))


def levels(findings):
    return [f.level for f in findings]


# Recognising drafts by file name.


@pytest.mark.parametrize(
    ("name", "kind", "number", "complex_topic"),
    [
        ("first-home-guide.md", "guide", None, False),
        ("first-home-email-1.md", "email", 1, False),
        ("investing-email-3.md", "email", 3, False),
        ("complex-structures-email-2.md", "email", 2, True),
        ("lunch-and-learn-invitation.md", "invitation", None, False),
        ("presentation-slides.md", "slides", None, False),
    ],
)
def test_kind_from_file_name(name, kind, number, complex_topic):
    result = kind_of(Path(name))
    assert (result.kind, result.number, result.complex_topic) == (kind, number, complex_topic)


# Clean drafts pass.


@pytest.mark.parametrize(
    ("text", "name"),
    [
        (GOOD_GUIDE, "first-home-guide.md"),
        (GOOD_EMAIL_1, "first-home-email-1.md"),
        (GOOD_INVITATION, "lunch-and-learn-invitation.md"),
        (GOOD_COMPLEX_EMAIL, "complex-structures-email-2.md"),
    ],
    ids=["guide", "email-1", "invitation", "complex-email"],
)
def test_clean_drafts_have_no_failures(text, name):
    assert FAIL not in levels(check(text, name))


# Each wording rule catches what it should.


@pytest.mark.parametrize(
    ("sentence", "level", "section"),
    [
        ("You should buy before prices rise.", FAIL, "A"),
        ("We recommend a fixed loan.", FAIL, "A"),
        ("This is the best option for most buyers.", FAIL, "A"),
        ("Approval is guaranteed.", FAIL, "A"),
        ("You will save thousands.", FAIL, "A"),
        ("Act now, as places are limited.", FAIL, "A"),
        ("Variable loans start at 5.9% p.a. with some lenders.", FAIL, "A"),
        ("The comparison rate is 6.1 per cent.", FAIL, "A"),
        ("You will need to provide ID.", CHECK, "A"),
        ("Interest rates can change over time.", CHECK, "A"),
        ("The grant is $10,000 for eligible buyers.", CHECK, "B"),
        ("Many lenders ask for a 20% deposit.", CHECK, "B"),
        ("Book your spot now!!", FAIL, "C"),
        ("Talk it over with your husband or wife.", FAIL, "D"),
        ("Each buyer brings his own documents.", FAIL, "D"),
        ("Ideal for young professionals.", FAIL, "D"),
        ("A plan for when you start a family.", FAIL, "D"),
        ("Doctors earn enough to buy sooner.", FAIL, "D"),
        ("Call me on 0400 000 000.", FAIL, "F"),
        ("Read more at https://bit.ly/abc123", FAIL, "H"),
        ("Read more at http://example.test/guide", FAIL, "H"),
        ("Read the guide [here](https://example.test/guide).", FAIL, "H"),
        ("Click here to read the guide.", FAIL, "H"),
        ("The grant is [XX] for each buyer.", FAIL, "H"),
        ("Book a FREE session today.", CHECK, "C"),
    ],
)
def test_wording_rules(sentence, level, section):
    findings = check(f"{sentence}\n\n{DISCLAIMER}\n", "first-home-guide.md")
    assert any(f.level == level and f.section == section for f in findings), findings


@pytest.mark.parametrize(
    "sentence",
    [
        "You should speak to an accountant before deciding.",
        "You should get independent advice.",
        "A broker can explain your options.",
        "Talk to your partner or co-buyer about your budget.",
        "Rules change, so check the official website.",
        "Read the guide at https://example.test/guide",
        "The GP clinic team is welcome to join.",
        "Our session covers the basics in 15 minutes.",
    ],
)
def test_safe_sentences_are_not_failed(sentence):
    findings = check(f"{sentence}\n\n{DISCLAIMER}\n", "first-home-guide.md")
    assert FAIL not in levels(findings), findings


# Structure rules.


def test_missing_disclaimer_fails():
    findings = check("A short guide with no disclaimer.", "first-home-guide.md")
    assert any("No disclaimer" in f.message for f in findings)


def test_exact_disclaimer_is_enforced_when_given():
    exact = "This is general information only and is not credit advice. ACL 000000."
    findings = check_draft(f"Some text.\n\n{DISCLAIMER}\n", Path("guide.md"), exact)
    assert any("missing or altered" in f.message for f in findings)
    findings = check_draft(f"Some text.\n\n{exact}\n", Path("guide.md"), exact)
    assert not any("missing or altered" in f.message for f in findings)


def test_disclaimer_wording_is_not_scanned_as_advice():
    text = "A short note.\n\nDisclaimer: You should consider whether this suits you.\n"
    assert FAIL not in levels(check(text, "first-home-guide.md"))


def test_placeholder_disclaimer_is_a_check():
    text = "A short note.\n\nDisclaimer: [PLACEHOLDER DISCLAIMER]\n"
    findings = check(text, "first-home-guide.md")
    assert any(f.level == CHECK and "Placeholder" in f.message for f in findings)


def test_email_needs_subject_and_unsubscribe():
    findings = check(f"Hello there.\n\n{DISCLAIMER}\n", "first-home-email-2.md")
    messages = " ".join(f.message for f in findings)
    assert "Subject:" in messages
    assert "unsubscribe" in messages


def test_fake_reply_subject_fails():
    text = GOOD_EMAIL_1.replace("Subject: Your", "Subject: Re: Your")
    assert any("reply or forward" in f.message for f in check(text, "first-home-email-1.md"))


def test_first_email_must_link_to_guide():
    text = GOOD_EMAIL_1.replace("https://example.test/first-home-guide", "the guide")
    findings = check(text, "first-home-email-1.md")
    assert any("link to the guide" in f.message for f in findings)


def test_later_emails_do_not_need_the_guide_link():
    text = GOOD_EMAIL_1.replace("https://example.test/first-home-guide", "the guide")
    findings = check(text, "first-home-email-2.md")
    assert not any("link to the guide" in f.message for f in findings)


def test_invitation_needs_opt_out():
    text = GOOD_INVITATION.replace("If you would prefer not to hear from me again", "Thanks")
    findings = check(text, "lunch-and-learn-invitation.md")
    assert any("opt out" in f.message for f in findings)


def test_complex_topic_must_refer_to_adviser():
    text = GOOD_COMPLEX_EMAIL.replace(
        "so you should speak to an accountant or licensed\nadviser before deciding",
        "so read the rules carefully",
    )
    findings = check(text, "complex-structures-email-2.md")
    assert any("accountant or adviser" in f.message for f in findings)


def test_long_guide_is_flagged():
    text = "# Guide\n\n" + "Plain words in a short sentence here. " * 80 + f"\n\n{DISCLAIMER}"
    findings = check(text, "first-home-guide.md")
    assert any("may not fit on one page" in f.message for f in findings)


def test_jargon_must_be_explained():
    text = f"You may need to pay LMI.\n\n{DISCLAIMER}"
    assert any(f.excerpt == "LMI" for f in check(text, "first-home-guide.md"))
    text = f"You may need to pay LMI (lenders mortgage insurance).\n\n{DISCLAIMER}"
    assert not any(f.excerpt == "LMI" for f in check(text, "first-home-guide.md"))


def test_reading_grade():
    easy = "We help you buy a home. It is not hard. We can talk it through."
    hard = (
        "Prospective purchasers considering residential property acquisitions should "
        "investigate comprehensive documentation requirements, eligibility considerations, "
        "and administrative obligations associated with concessional arrangements."
    )
    assert reading_grade(easy) < 6
    assert reading_grade(hard) > 12


def test_findings_have_line_numbers():
    findings = check(f"Line one.\nApproval is guaranteed.\n\n{DISCLAIMER}", "guide.md")
    assert any(f.line == 2 and "Promised" in f.message for f in findings)


# The command.


def test_command_exit_codes(tmp_path, capsys):
    (tmp_path / "first-home-email-1.md").write_text(GOOD_EMAIL_1)
    assert main([str(tmp_path)]) == 0
    (tmp_path / "first-home-guide.md").write_text(f"Approval is guaranteed.\n\n{DISCLAIMER}")
    assert main([str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "2 drafts: 1 clean, 0 with checks only, 1 with failures" in output
    assert "ready for human review, not approved" in output
