"""Reject any agent output that appears to contain a person's name.

This check is deliberately strict. A false alarm costs one retry, but a name
that slips through would be a privacy incident. It never returns, logs, or
raises the text it matched, only the kind of problem and the field it was in.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

TITLE_PATTERN = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Miss|Mx|Prof|Professor|A/Prof)\b\.?\s+[A-Za-z]")
INITIAL_PATTERN = re.compile(r"\b[A-Z]\.\s?[A-Z][a-z]+")
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z'’-]*")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# Capitalised words that are fine in the middle of a sentence.
COMMON_CAPITALS = {
    "i", "gp", "ahpra", "smsf", "acl", "abn", "pdf", "wa", "nsw", "vic", "qld", "sa", "tas",
    "nt", "act", "australia", "australian", "western", "perth", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march",
    "april", "may", "june", "july", "august", "september", "october", "november", "december",
}  # fmt: skip

# Common given names, used to catch a name at the start of a sentence.
COMMON_GIVEN_NAMES = {
    "adam", "alex", "alice", "amanda", "amy", "andrew", "angela", "anna", "anthony", "ben",
    "benjamin", "brian", "caitlin", "charlotte", "chris", "christine", "claire", "daniel",
    "david", "deborah", "elizabeth", "emily", "emma", "eric", "gary", "george", "grace",
    "hannah", "helen", "henry", "ian", "jack", "jacob", "james", "jane", "jason", "jennifer",
    "jessica", "jim", "joanne", "john", "jonathan", "joseph", "joshua", "julia", "karen",
    "kate", "katherine", "kevin", "laura", "lauren", "lee", "linda", "lisa", "lucy", "luke",
    "margaret", "maria", "mark", "mary", "matthew", "megan", "melissa", "michael", "michelle",
    "natalie", "nicholas", "nicole", "olivia", "patricia", "paul", "peter", "rachel",
    "rebecca", "richard", "robert", "ryan", "samantha", "sarah", "scott", "simon", "sophie",
    "stephen", "steven", "susan", "thomas", "timothy", "tom", "victoria", "william", "wei",
    "mei", "ling", "priya", "raj", "ahmed", "mohammed", "fatima", "aisha", "tran", "nguyen",
}  # fmt: skip


class NameFoundError(Exception):
    """Raised when output looks like it contains a name. Never includes the text itself."""


@dataclass(frozen=True)
class NameCheckResult:
    found: bool
    reasons: tuple[str, ...] = ()


def _allowed_words(allowed_terms: Iterable[str]) -> set[str]:
    words = set(COMMON_CAPITALS)
    for term in allowed_terms:
        words.update(word.lower() for word in WORD_PATTERN.findall(term))
    return words


def _is_allowed(word: str, allowed: set[str]) -> bool:
    lowered = word.lower().replace("’", "'")
    if lowered.endswith("'s"):
        lowered = lowered[:-2]
    return lowered in allowed or lowered.rstrip("s") in allowed


def check_for_names(text: str, allowed_terms: Iterable[str] = ()) -> NameCheckResult:
    """Check one piece of text. Allowed terms are the organisation's own name and suburb."""
    allowed = _allowed_words(allowed_terms)
    reasons: set[str] = set()

    if TITLE_PATTERN.search(text):
        reasons.add("title followed by a word")
    if INITIAL_PATTERN.search(text):
        reasons.add("initial followed by a surname")

    for sentence in SENTENCE_SPLIT.split(text):
        words = WORD_PATTERN.findall(sentence)
        for position, word in enumerate(words):
            if _is_allowed(word, allowed):
                continue
            base = word.lower().replace("’", "'").removesuffix("'s")
            if position == 0:
                if base in COMMON_GIVEN_NAMES:
                    reasons.add("given name at start of sentence")
            elif word[0].isupper():
                reasons.add("capitalised word in the middle of a sentence")
    return NameCheckResult(found=bool(reasons), reasons=tuple(sorted(reasons)))


def ensure_no_names(fields: dict[str, str], allowed_terms: Iterable[str] = ()) -> None:
    """Check every text field and raise if any looks like it has a name."""
    problems = []
    for field, text in fields.items():
        result = check_for_names(text, allowed_terms)
        if result.found:
            problems.append(f"{field}: {', '.join(result.reasons)}")
    if problems:
        raise NameFoundError("Output rejected, possible name in " + "; ".join(problems))
