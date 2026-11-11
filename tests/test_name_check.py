"""Tests for the name check. Every name here is made up."""

import pytest

from org_research_agent.name_check import (
    NameFoundError,
    check_contact,
    check_for_names,
    check_source_url,
    ensure_no_names,
    link_may_name_person,
    looks_like_team_page,
    mask_names,
)

# What the program would pass in: the org's own name, suburbs, and local places.
ALLOWED = [
    "Testville Family Dental",
    "Victoria Park",
    "East Victoria Park",
    "Albany Highway",
    "Curtin University",
]

# Realistic name-free text, in the style of clinic websites and agent output.
CLEAN = [
    "The clinic bulk bills Medicare and accepts DVA and NDIS clients.",
    "Our team includes three Physiotherapists and a Pilates instructor.",
    "We are located on Albany Highway near the Curtin University bus stop.",
    "Our Principal Dentist has over 20 years of experience.",
    "We offer Invisalign, implants and general dentistry.",
    "We accept HICAPS and all major health funds including HBF and Bupa.",
    "Our GPs hold FRACGP qualifications.",
    "Appointments are available through HotDoc.",
    "The practice is accredited by AGPAL.",
    "We treat WorkCover and motor vehicle injury claims.",
    "Open Saturday mornings in East Victoria Park.",
    "Meet Our Friendly Team",
    "New Patients Welcome",
    "Book Online Now",
    "Our Services",
    "We are a family-owned practice.",
    "The pharmacy has a team of pharmacists and pharmacy assistants.",
    "Women's Health and Pelvic Floor Physiotherapy",
    "Sports Injury Clinic",
    "Remedial Massage and Dry Needling",
    "Please note: we do not accept unsolicited marketing emails.",
    "Our dentists are registered with AHPRA.",
    "Telehealth consultations are available.",
    "Flu vaccinations available at the pharmacy.",
    "The team page lists eight practitioners.",
    "Staff size is not stated on the website.",
    "Children's Dental Benefits Schedule accepted.",
    "Afterpay and EFTPOS available.",
    "Located inside the Park Centre shopping centre.",
    "Free parking is available at the rear.",
    "Our Chiropractors use gentle techniques.",
    "Wheelchair Access",
    "COVID-19 Safety Plan",
    "Find Us",
    "Testville Family Dental has five dentists.",
    "We treat patients with MS and other conditions.",
    "Parking is at 12 Albany Dr, Victoria Park.",
    "Please mark the form and bring it to reception.",
]

# Text with made-up names, including disguised forms.
WITH_NAMES = [
    "Dr Patel is our principal dentist.",
    "Meet Dr. Quinn and the team.",
    "Sarah leads the hygiene team.",
    "The clinic was founded by Marcus and two partners.",
    "Contact J. Whitfield for bookings.",
    "Our physio is Priya Nair.",
    "Sarah's team has three dentists.",
    "Whitfield leads the team.",
    "Okonkwo is the senior physiotherapist.",
    "Principal dentist: Nguyen.",
    "SARAH JONES, PRINCIPAL DENTIST",
    "Our pharmacist sarah can help.",
    "The owner, O'Brien, has 20 years of experience.",
    "Ask for Smith-Jones at reception.",
    "Élodie is our osteopath.",
    "王伟 is our GP.",
    "Our dentist is S a r a h.",
    "Our dentist is S-a-r-a-h.",
    "Sa​rah runs the clinic.",
    "Ｓａｒａｈ is our GP.",
    "Mr Tan and Mrs Tan run the pharmacy.",
    "Prof. Adeyemi consults on Tuesdays.",
    "A/Prof Lim is a visiting specialist.",
    "The clinic has 3 GPs, including Wei Zhang.",
    "Email sarah.whitfield@example.test for bookings.",
    "Call Raj on 0412 345 678.",
    "Physiotherapist Hamid Rezaei joined in 2024.",
    "dr okafor sees children.",
    "Treatment by Dr Lee.",
    "Ms Kowalczyk is the practice manager.",
    "Our GP, Dr Ana Souza, is available Mondays.",
    "Founded by D'Souza in 2010.",
    "Grace runs the front desk.",
]

FALSE_ALARM_LIMIT = 0.10


@pytest.mark.parametrize("text", WITH_NAMES)
def test_every_name_is_flagged(text):
    assert check_for_names(text, ALLOWED).found


def test_false_alarm_rate_is_low():
    flagged = [text for text in CLEAN if check_for_names(text, ALLOWED).found]
    rate = len(flagged) / len(CLEAN)
    print(
        f"\nFalse alarms: {len(flagged)} of {len(CLEAN)} ({rate:.0%}). "
        f"Names missed: 0 of {len(WITH_NAMES)}."
    )
    assert rate <= FALSE_ALARM_LIMIT, flagged


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("Dr Patel is here.", "title followed by a word"),
        ("dr patel is here.", "title followed by a word"),
        ("Contact J. Whitfield today.", "initial followed by a word"),
        ("Our dentist is S a r a h.", "spaced-out letters"),
        ("Sa​rah is here.", "hidden characters"),
        ("王伟 is our GP.", "non-Latin letters"),
        ("Email info@example.test today.", "email address"),
        ("Call 0412 345 678.", "mobile number"),
        ("Token " + "x" * 40, "unusually long token"),
        ("Sarah is here.", "given name"),
        ("Whitfield is here.", "unknown capitalised word"),
    ],
)
def test_reason_names_the_kind_of_problem(text, reason):
    assert reason in check_for_names(text).reasons


def test_org_name_containing_a_person_is_allowed_only_as_a_whole():
    allowed = ["Dr Sarah Whitfield Dental"]
    assert not check_for_names("Dr Sarah Whitfield Dental has four dentists.", allowed).found
    assert check_for_names("Sarah is the principal dentist.", allowed).found
    assert check_for_names("Dr Whitfield is the principal dentist.", allowed).found


def test_org_words_are_allowed_only_when_given():
    text = "Welcome to Testville Family Dental."
    assert not check_for_names(text, ALLOWED).found
    assert check_for_names(text).found


def test_error_never_contains_the_name():
    with pytest.raises(NameFoundError) as error:
        ensure_no_names({"evidence_quote": "Meet Dr Patel and Sarah Jones."}, ALLOWED)
    message = str(error.value)
    assert "evidence_quote" in message
    for name in ("Patel", "Sarah", "Jones"):
        assert name not in message


def test_checks_every_field():
    fields = {"fit_reason": "Three dentists on staff.", "evidence_quote": "Ask for Dr Patel."}
    with pytest.raises(NameFoundError, match="evidence_quote"):
        ensure_no_names(fields, ALLOWED)


def test_long_field_is_rejected():
    with pytest.raises(NameFoundError, match="too long"):
        ensure_no_names({"fit_reason": "three dentists " * 40}, max_length=100)


def test_clean_fields_pass():
    ensure_no_names({"fit_reason": "Three dentists on staff."}, ALLOWED)


@pytest.mark.parametrize(
    "contact",
    [
        "info@testvillefamilydental.example",
        "reception@example.test",
        "testvillefamilydental@example.test",
        "Phone (08) 9000 0000",
        "1300 000 000",
    ],
)
def test_generic_contacts_pass(contact):
    assert not check_contact(contact, ALLOWED).found


@pytest.mark.parametrize(
    "contact",
    [
        "sarah@example.test",
        "s.whitfield@example.test",
        "whitfield.s@example.test",
        "0412 345 678",
        "+61 412 345 678",
    ],
)
def test_personal_contacts_are_flagged(contact):
    assert check_contact(contact, ALLOWED).found


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/",
        "https://example.test/our-team",
        "https://example.test/about-us/our-team/",
        "https://example.test/services/physiotherapy.html",
        "https://example.test/team/physiotherapists",
    ],
)
def test_ordinary_urls_pass(url):
    assert not check_source_url(url).found


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/our-team/sarah-whitfield",
        "https://example.test/team/okonkwo",
        "https://example.test/dr-patel",
        "https://example.test/practitioners?name=whitfield",
        "https://example.test/staff/profile-123/whitfield",
    ],
)
def test_profile_urls_are_flagged(url):
    assert check_source_url(url).found


@pytest.mark.parametrize(
    "url, team",
    [
        ("https://example.test/our-team", True),
        ("https://example.test/about-us/meet-the-team/", True),
        ("https://example.test/team/index.html", True),
        ("https://example.test/practitioners.html", True),
        ("https://example.test/people", True),
        ("https://example.test/", False),
        ("https://example.test/about", False),
        ("https://example.test/about-us/meet-our-support-team/", True),
        ("https://example.test/doctors-team-testvale-medical-centre/", True),
        ("https://example.test/our-gps", True),
        ("https://example.test/meet_the_dentists.php", True),
        # A team word anywhere blocks the page. These may not list staff, but a staff
        # party post often names people, and missing a page costs less than reading one.
        ("https://example.test/services/team-building.html", True),
        ("https://example.test/news/our-staff-party-2026", True),
        ("https://example.test/services/teeth-whitening", False),
        ("https://example.test/steamed-towels", False),
        ("https://example.test/contact.html", False),
    ],
)
def test_team_page_urls(url, team):
    assert looks_like_team_page(url) is team


# Masking names before the AI sees a page.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Dr Sarah Chen and Kyle Tam", "Dr [name] [name] and [name] [name]"),
        ("dr wei li", "dr [name] [name]"),
        ("Ms Jo", "Ms [name]"),
        ("Call 0412 345 678", "Call [mobile number]"),
        ("Email sarah@clinic.test", "Email [name]"),
        ("Email info@clinic.test", "Email info@clinic.test"),
        (
            "Bulk billing for children, Monday to Friday.",
            "Bulk billing for children, Monday to Friday.",
        ),
        ("Our team of 6 at Archer Street Physio", "Our team of 6 at Archer Street Physio"),
        ("Archer Physio and Archer", "Archer Physio and Archer"),
        ("张伟 is here", "[name] is here"),
    ],
)
def test_mask_names(text, expected):
    masked, _ = mask_names(text, ("Archer Street Physio", "Archer Physio"))
    assert masked == expected


def test_mask_names_counts_replacements():
    assert mask_names("Dr Sarah Chen", ())[1] == 2
    assert mask_names("Open Monday", ())[1] == 0


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://a.test/about-us/", False),
        ("https://a.test/contact-us/", False),
        ("https://a.test/root-canal-treatment/", False),
        ("https://a.test/about-us/kyle-tam/", True),
        ("https://a.test/about-us/dr-kyle-tam/", True),
        ("https://a.test/our-team/", True),
        ("https://a.test/archer-street-physio/", False),
    ],
)
def test_link_may_name_person(url, expected):
    assert link_may_name_person(url, ("Archer Street Physio",)) is expected
