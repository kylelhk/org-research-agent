"""Reject agent output that may contain a person's name or personal details.

The core rule: every capitalised word must be a known word, a known health
term, or part of the organisation's own name or suburb. Anything else is
treated as a possible name. Extra checks catch titles, initials, disguised
names, personal emails, mobile numbers, and staff profile URLs.

The check is deliberately strict, since a missed name is a privacy incident
and a false alarm only means a manual check. It never returns, logs, or
raises the text it matched, only the kind of problem and the field it was in.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

MAX_FIELD_LENGTH = 400

# Ordinary words that are fine when capitalised, for example at the start of a
# sentence or in a heading. This is an allowlist, so it must not contain names.
ORDINARY_WORDS = set(
    """
    a about accept accepted accepting access accredited accreditation adult adults after
    aged all allied also an and any appointment appointments approximately are area as
    assistant assistants associate at available based be been benefits billed billing bills
    book booking bookings both bulk bus but by call can care centre centres center check
    checks checkup checkups children chiropractic chiropractor chiropractors claim claims
    clinic clinics clinical clinician clinicians closed co conditions consult consultation
    consultations contact cosmetic currently day days dental dentist dentists dentistry
    dietitian dietitians director disability do doctor doctors does dry each east eight
    eleven emails email emergency employ employs established evening evenings every exercise
    experience experienced family fax fees find five floor flu following for forms founder four
    free friendly from full fund funds gap general gentle get has have head health
    healthcare help here highway home hospital hours how hygiene hygienist hygienists
    implant implants in including information injury injuries instructor insurance is it
    its join kids lead learn least level listed lists located location locations main major
    manager marketing massage medical meet member members men mental more morning mornings
    most motor multiple needling new nine no north not note now nurse nurses number
    occupational of offer offers on one online only open opening or oral orthodontic
    orthodontics orthodontist orthodontists osteopath osteopaths osteopathy other our over
    owned owner page parking part partner partners patient patients pelvic per phone pharmacies
    pharmacist pharmacists pharmacy physio physios physiologist physiologists physiotherapist
    physiotherapists physiotherapy plan please podiatrist podiatrists podiatry policy practice
    practices practitioner practitioners prescriptions principal privacy private psychologist
    psychologists psychology public qualified qualifications rear receptionist receptionists
    referral referrals registered rehabilitation remedial road safety schedule senior seniors
    service services seven several six skin south specialist specialists speech sports staff
    stated states stop street suite support surgeon surgeons surgery team teams techniques
    telehealth ten that the their therapist therapists therapy there these they this three
    time to total travel treat treatment treatments twelve two under unit unknown
    unsolicited up urgent us vaccination vaccinations vehicle we website welcome wellbeing
    west wheelchair which who why with women years you your
    ask choose enquire if make please read request see so then visit view was were what
    when where while will yes
    monday tuesday wednesday thursday friday saturday sunday january february march april
    may june july august september october november december
    all rights reserved copyright founded since dear regards kind thank thanks terms
    conditions payment payments options news blog gallery reviews testimonials links
    resources forms fillings crowns bridges veneers whitening teeth tooth root canal
    mouthguards mouthguard cleaning clean gum gums wisdom removal extraction extractions
    dentures sleep orthotics foot feet ankle knee back neck shoulder pain headaches
    vaccinations scripts compounding dispensary vitamins counselling assessment
    assessments rebates rebate cancellation hydrotherapy
    """.split()
)

# Proper nouns, brands, and abbreviations common on Australian health websites.
KNOWN_TERMS = set(
    """
    i medicare ndis dva hicaps workcover hbf bupa medibank nib hcf ahm gmhba ahpra agpal
    qip racgp fracgp acrrm ada apa aca psa pilates invisalign hotdoc healthengine mygov
    eftpos afterpay visa mastercard amex covid australia australian western perth wa nsw
    vic qld sa tas nt act gp smsf acl abn pdf faq ecg mri ct ot rn en bds dds mbbs bsc phd
    fracds cdbs ms tel ph st rd ave hwy pde cres
    """.split()
)

# Common given names from many backgrounds. Used to catch names that are not
# capitalised and to stop a name being allowed because it is in an org name.
GIVEN_NAMES = set(
    """
    adam aiden alex alexander alice alicia amanda amelia amy andrew angela anna anthony
    benjamin brian caitlin charlotte chloe chris christine christopher claire daniel david
    deborah elizabeth ella emily emma eric ethan gary george hannah harry helen henry ian
    isabella jacob james jane jason jennifer jessica jim joanne john jonathan joseph joshua
    julia karen kate katherine kevin laura lauren liam linda lisa lucy luke marcus margaret
    maria mary matthew megan melissa michael michelle natalie nicholas nicole noah oliver
    olivia patricia paul peter rachel rebecca richard robert ryan samantha sarah scott simon
    sophie stephen steven susan thomas timothy tom william zoe
    wei li ming jing xin hui yan ling mei lei jun hao yu chen zhang wang liu
    minh linh anh thanh huong trang hoa tuan duc nguyen tran
    priya raj rahul amit anil sanjay deepak ravi sunita anjali pooja neha arjun vikram
    kavya aditya rohan sneha
    mohammed muhammad ahmed ali omar hassan hussein fatima aisha layla mariam yusuf ibrahim
    khalid zainab noor hamid
    jose juan carlos luis ana sofia
    yuki hiro kenji aiko
    grace mark jack lee victoria rose joy faith hope ruby jade amber holly hunter dean grant
    frank ray guy sue pat rob nick max sam bill hung min
    """.split()
)

# Given names that are also ordinary English words. These are only flagged when
# capitalised, to avoid rejecting sentences like "please mark the form".
AMBIGUOUS_NAMES = set(
    """
    grace mark jack lee victoria rose joy faith hope ruby jade amber holly hunter dean grant
    frank ray guy sue pat rob nick max sam bill hung min
    """.split()
)

TITLE_WORDS = {"dr", "drs", "mr", "mrs", "mx", "ms", "prof", "doctor", "professor"}

# Mailbox names that are generic, not personal.
GENERIC_MAILBOXES = set(
    """
    info admin administration reception enquiries enquiry hello contact contactus bookings
    booking book appointments appointment office mail email team practice frontdesk front
    desk care clinic accounts account help support manager practicemanager pharmacy dental
    dentist physio health medical noreply reply feedback billing referrals referral records
    privacy careers jobs hr recruitment news service services orders scripts
    """.split()
)

# Path segments that usually lead to a page about one staff member.
TEAM_SEGMENTS = set(
    """
    team our-team meet-the-team the-team team-members staff our-staff people our-people
    practitioners our-practitioners practitioner doctors our-doctors doctor dentists
    our-dentists dentist clinicians providers our-providers physiotherapists
    our-physiotherapists pharmacists profile profiles bio bios
    """.split()
)
# A word in an address segment, such as "team" in "doctors-team-carlisle", that marks
# a page about the practice's people however the rest of the address is worded.
TEAM_WORDS = set(
    """
    team teams staff people practitioners doctors dentists clinicians providers
    physiotherapists pharmacists gps
    """.split()
)
URL_FILE_WORDS = {"html", "htm", "php", "aspx", "index"}
NAME_QUERY_KEYS = {"name", "practitioner", "doctor", "dentist", "staff", "provider", "clinician"}

# Titles that are never ordinary words, in any letter case, followed by a word.
TITLE_ANY_CASE = re.compile(r"(?i)\b(?:dr|drs|mr|mrs|mx|prof)\b\.?\s+[^\W\d_]")
# Titles that are also ordinary words, so only flagged when written as a title.
TITLE_CASED = re.compile(r"\b(?:Ms|Miss|Doctor|Professor|Sir|Dame|Lady)\b\.?\s+[A-Z]")
INITIAL = re.compile(r"\b[A-Z]\.\s?[A-Z][a-z]")
# Three or more single letters split by spaces, dots, dashes, or underscores.
SPACED_LETTERS = re.compile(r"(?<![^\W\d_])(?:[^\W\d_][ .\-_]){2,}[^\W\d_](?![^\W\d_])")
LONG_TOKEN = re.compile(r"\S{30,}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
MOBILE = re.compile(r"(?:\+?61[\s-]?|\b0)4(?:[\s-]?\d){8}\b")
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*'?")
ALLOWED_CONTROL = {"\n", "\t", "\r"}


class NameFoundError(Exception):
    """Raised when output may contain a name. Never includes the text itself."""


@dataclass(frozen=True)
class NameCheckResult:
    found: bool
    reasons: tuple[str, ...] = ()


def _result(reasons: set[str]) -> NameCheckResult:
    return NameCheckResult(found=bool(reasons), reasons=tuple(sorted(reasons)))


def _base(word: str) -> str:
    """Lower-case a word and drop a possessive ending."""
    word = word.lower().replace("’", "'")
    if word.endswith("'s"):
        return word[:-2]
    return word.rstrip("'")


def _is_known(base: str, allowed: set[str]) -> bool:
    candidates = {base}
    if base.endswith("es"):
        candidates.add(base[:-2])
    if base.endswith("s"):
        candidates.add(base[:-1])
    return bool(candidates & allowed)


def _has_hidden_characters(text: str) -> bool:
    return any(
        unicodedata.category(char) in {"Cf", "Co", "Cn", "Cc"} and char not in ALLOWED_CONTROL
        for char in text
    )


def _has_non_latin_letters(text: str) -> bool:
    return any(
        char.isalpha() and not unicodedata.name(char, "").startswith("LATIN") for char in text
    )


def _mask_allowed_terms(text: str, allowed_terms: Iterable[str]) -> tuple[str, set[str]]:
    """Replace the organisation's own name and suburbs, and collect their safe words."""
    terms = sorted({term.strip() for term in allowed_terms if term.strip()}, key=len, reverse=True)
    extra_words = set()
    for term in terms:
        pattern = re.compile(r"(?<![^\W_])" + re.escape(term) + r"(?![^\W_])", re.IGNORECASE)
        text = pattern.sub(" the ", text)
        for word in WORD.findall(term):
            base = _base(word)
            # A person's name inside an org name is still not allowed on its own.
            if base not in GIVEN_NAMES and base not in TITLE_WORDS:
                extra_words.add(base)
    return text, extra_words


def check_for_names(text: str, allowed_terms: Iterable[str] = ()) -> NameCheckResult:
    """Check one piece of free text. Allowed terms are the org's own name and suburbs."""
    reasons: set[str] = set()

    if _has_hidden_characters(text):
        reasons.add("hidden characters")
    # Fold look-alike forms (such as full-width letters) into plain ones.
    text = unicodedata.normalize("NFKC", text)
    if _has_non_latin_letters(text):
        reasons.add("non-Latin letters")
    if EMAIL.search(text):
        reasons.add("email address")
    if MOBILE.search(text):
        reasons.add("mobile number")
    if LONG_TOKEN.search(text):
        reasons.add("unusually long token")

    text, extra_words = _mask_allowed_terms(text, allowed_terms)
    allowed = ORDINARY_WORDS | KNOWN_TERMS | extra_words

    if TITLE_ANY_CASE.search(text) or TITLE_CASED.search(text):
        reasons.add("title followed by a word")
    if INITIAL.search(text):
        reasons.add("initial followed by a word")
    if SPACED_LETTERS.search(text):
        reasons.add("spaced-out letters")

    for word in WORD.findall(text):
        base = _base(word)
        capitalised = word[0].isupper()
        if base in GIVEN_NAMES and (capitalised or base not in AMBIGUOUS_NAMES):
            reasons.add("given name")
        elif capitalised and not _is_known(base, allowed):
            reasons.add("unknown capitalised word")
    return _result(reasons)


NAME_MASK = "[name]"
# What may sit between two parts of one name: a space, hyphen, or apostrophe.
NAME_JOIN = re.compile(r"[ \t\-'’]{1,2}")
TITLE_THEN_WORD = re.compile(
    r"(?i)\b(dr|drs|mr|mrs|mx|ms|miss|prof|doctor|professor)(\.?\s+)([^\W\d_][\w'’-]*)"
)


def _protected_spans(text: str, allowed_terms: Iterable[str]) -> list[tuple[int, int]]:
    """Where the organisation's own name and places appear, so they are left alone."""
    spans = []
    for term in {term.strip() for term in allowed_terms if term.strip()}:
        pattern = re.compile(r"(?<![^\W_])" + re.escape(term) + r"(?![^\W_])", re.IGNORECASE)
        spans.extend(match.span() for match in pattern.finditer(text))
    return spans


def _is_possible_name(word: str, allowed: set[str]) -> bool:
    """The same word test as check_for_names, for one word."""
    base = _base(word)
    if _has_non_latin_letters(word):
        return True
    if base in GIVEN_NAMES and (word[0].isupper() or base not in AMBIGUOUS_NAMES):
        return True
    return word[0].isupper() and not _is_known(base, allowed)


def mask_names(text: str, allowed_terms: Iterable[str] = ()) -> tuple[str, int]:
    """Replace every word the output check would reject with [name], before the AI sees it.

    Uses the same strict rule as check_for_names, so many ordinary words (brand names,
    menu labels) are replaced too. That is the intended trade: the agent only needs
    the practice type, a stated staff number, and published contact details, and a name
    that is never shown to the AI cannot be stored, logged, or repeated by it.
    Personal emails and mobile numbers are replaced the same way.
    Returns the masked text and how many replacements were made.
    """
    allowed_terms = tuple(allowed_terms)
    text = unicodedata.normalize("NFKC", text)
    count = 0

    def replace_email(match: re.Match) -> str:
        nonlocal count
        if check_contact(match.group(), allowed_terms).found:
            count += 1
            return NAME_MASK
        return match.group()

    def replace_mobile(match: re.Match) -> str:
        nonlocal count
        count += 1
        return "[mobile number]"

    def replace_after_title(match: re.Match) -> str:
        nonlocal count
        count += 1
        return match.group(1) + match.group(2) + NAME_MASK

    text = EMAIL.sub(replace_email, text)
    text = MOBILE.sub(replace_mobile, text)
    text = TITLE_THEN_WORD.sub(replace_after_title, text)

    _, extra_words = _mask_allowed_terms(text, allowed_terms)
    allowed = ORDINARY_WORDS | KNOWN_TERMS | TITLE_WORDS | extra_words | {"miss"}
    protected = _protected_spans(text, allowed_terms)
    pieces, last, name_end = [], 0, None
    for match in WORD.finditer(text):
        start, end = match.span()
        word = match.group()
        if word == "name" and text[start - 1 : end + 1] == NAME_MASK:
            name_end = end + 1  # Already masked after a title.
            continue
        if any(a <= start and end <= b for a, b in protected):
            name_end = None
            continue
        # A capitalised word straight after a masked one is treated as part of the same
        # name, so a surname that is also an ordinary or place word ("Day", "Park") goes too.
        joined = (
            name_end is not None
            and word[0].isupper()
            and NAME_JOIN.fullmatch(text[name_end:start]) is not None
        )
        if joined or _is_possible_name(word, allowed):
            pieces.append(text[last:start] + NAME_MASK)
            last = name_end = end
            count += 1
        else:
            name_end = None
    pieces.append(text[last:])
    return "".join(pieces), count


def check_contact(value: str, allowed_terms: Iterable[str] = ()) -> NameCheckResult:
    """Check a published contact field. Generic mailboxes are fine, personal ones are not."""
    reasons: set[str] = set()
    squashed_terms = {re.sub(r"[^a-z]", "", term.lower()) for term in allowed_terms}
    squashed_terms.discard("")

    for match in EMAIL.finditer(value):
        local = match.group().split("@")[0].lower()
        letters = re.sub(r"[^a-z]", "", local)
        if letters and any(letters in term or term in letters for term in squashed_terms):
            continue
        tokens = [token for token in re.split(r"[^a-z]+", local) if token]
        safe = GENERIC_MAILBOXES | ORDINARY_WORDS | KNOWN_TERMS
        if not tokens or any(t in GIVEN_NAMES or t not in safe for t in tokens):
            reasons.add("possibly personal email")

    rest = check_for_names(EMAIL.sub(" ", value), allowed_terms)
    reasons.update(rest.reasons)
    return _result(reasons)


def check_source_url(url: str) -> NameCheckResult:
    """Check a source URL for names or a page about one staff member."""
    reasons: set[str] = set()
    parts = urlsplit(url)
    path = unquote(parts.path)
    query = parse_qs(parts.query)

    words = [word for word in re.split(r"[^a-z]+", (path + " " + unquote(parts.query)).lower())]
    for word in words:
        if word in TITLE_WORDS or (word in GIVEN_NAMES and word not in AMBIGUOUS_NAMES):
            reasons.add("name-like word in URL")

    if NAME_QUERY_KEYS & {key.lower() for key in query}:
        reasons.add("name field in URL query")

    segments = [segment for segment in path.lower().split("/") if segment]
    safe = ORDINARY_WORDS | KNOWN_TERMS | URL_FILE_WORDS
    for position, segment in enumerate(segments[:-1]):
        if segment in TEAM_SEGMENTS:
            following = [w for w in re.split(r"[^a-z]+", segments[position + 1]) if w]
            if any(word not in safe for word in following):
                reasons.add("looks like a staff profile page")
    return _result(reasons)


def looks_like_team_page(url: str) -> bool:
    """True if the URL's path looks like a team or staff page, such as /our-team/.

    Team pages list staff by name, so they are not read at all. This catches the page
    from its address alone, before anything is downloaded. A team word anywhere in a
    segment counts, so /meet-our-support-team/ and /doctors-team-carlisle/ are caught.
    Blocking an ordinary page by mistake costs little; reading a team page does not.
    """
    segments = [segment for segment in unquote(urlsplit(url).path).lower().split("/") if segment]
    if segments and segments[-1].rsplit(".", 1)[0] in URL_FILE_WORDS:
        segments = segments[:-1]
    names = [segment.rsplit(".", 1)[0] for segment in segments]
    return any(
        name in TEAM_SEGMENTS or TEAM_WORDS & set(re.split(r"[^a-z]+", name)) for name in names
    )


def link_may_name_person(url: str, allowed_terms: Iterable[str] = ()) -> bool:
    """True if a link's address may name a person or lead to a team page.

    Such links are left out of the list the agent sees, because the address itself
    can carry a name, such as /about-us/sarah-chen/. Besides the profile and team
    checks, an address segment made only of two to four unfamiliar words is treated
    as a possible name.
    """
    if check_source_url(url).found or looks_like_team_page(url):
        return True
    _, extra_words = _mask_allowed_terms("", allowed_terms)
    safe = ORDINARY_WORDS | KNOWN_TERMS | URL_FILE_WORDS | TITLE_WORDS | extra_words
    for segment in unquote(urlsplit(url).path).lower().split("/"):
        words = [word for word in re.split(r"[^a-z]+", segment.rsplit(".", 1)[0]) if word]
        if _has_non_latin_letters(segment):
            return True
        if 2 <= len(words) <= 4 and not any(_is_known(word, safe) for word in words):
            return True
    return False


def ensure_no_names(
    fields: Mapping[str, str],
    allowed_terms: Iterable[str] = (),
    max_length: int = MAX_FIELD_LENGTH,
) -> None:
    """Check every free-text field and raise if any may contain a name."""
    allowed_terms = tuple(allowed_terms)
    problems = []
    for field, text in fields.items():
        reasons = set(check_for_names(text, allowed_terms).reasons)
        if len(text) > max_length:
            reasons.add("text too long")
        if reasons:
            problems.append(f"{field}: {', '.join(sorted(reasons))}")
    if problems:
        raise NameFoundError("Output rejected, possible name in " + "; ".join(problems))
