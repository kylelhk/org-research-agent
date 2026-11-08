import pytest

from org_research_agent.name_check import NameFoundError, check_for_names, ensure_no_names

ORG = ["Testville Family Dental", "Testville"]

CLEAN = [
    "The practice lists three dentists and two hygienists.",
    "Our team of 4 GPs and 2 nurses is here to help.",
    "Staff size is not stated on the website.",
    "Testville Family Dental has five dentists.",
    "Open Monday to Friday in Perth, WA.",
]

WITH_NAMES = [
    ("Dr Patel is our principal dentist.", "title"),
    ("Meet Dr. Quinn and the team.", "title"),
    ("Sarah leads the hygiene team.", "given name"),
    ("The clinic was founded by Marcus and two partners.", "capitalised"),
    ("Contact J. Whitfield for bookings.", "initial"),
    ("Our physio is Priya Nair.", "capitalised"),
    ("Sarah's team has three dentists.", "given name"),
]


@pytest.mark.parametrize("text", CLEAN)
def test_clean_text_passes(text):
    assert not check_for_names(text, ORG).found


@pytest.mark.parametrize(("text", "kind"), WITH_NAMES)
def test_names_are_flagged(text, kind):
    result = check_for_names(text, ORG)
    assert result.found
    assert any(kind in reason for reason in result.reasons)


def test_organisation_words_are_allowed_only_when_given():
    text = "Welcome to Testville Family Dental."
    assert not check_for_names(text, ORG).found
    assert check_for_names(text).found


def test_error_never_contains_the_name():
    with pytest.raises(NameFoundError) as error:
        ensure_no_names({"evidence_quote": "Meet Dr Patel and Sarah Jones."}, ORG)
    message = str(error.value)
    assert "evidence_quote" in message
    for name in ("Patel", "Sarah", "Jones"):
        assert name not in message


def test_checks_every_field():
    fields = {"fit_reason": "Three dentists on staff.", "evidence_quote": "Ask for Dr Patel."}
    with pytest.raises(NameFoundError, match="evidence_quote"):
        ensure_no_names(fields, ORG)


def test_clean_fields_pass():
    ensure_no_names({"fit_reason": "Three dentists on staff."}, ORG)
