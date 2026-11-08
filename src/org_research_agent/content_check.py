"""Automated first pass over content drafts, before a person reviews them.

It checks Markdown or text drafts against the mechanical parts of
docs/content-review-checklist.md: advice and promise wording, rates and
figures, pressure, unsafe links, missing disclaimers and opt-outs, and
wording that assumes age, gender, or family. It cannot judge meaning or
check facts, so a clean result means "ready for human review", not approved.

Each finding is either FAIL (must be fixed) or CHECK (allowed only if a
person confirms it, for example a figure with a recorded source).

Drafts are recognised by file name:
    *guide*            a one-page guide
    *email-N*          email N of a sequence (the first must link to the guide)
    *invitation*       the lunch-and-learn invitation
    *slides*, *presentation*
A name containing "complex" marks the complex structures topic.
Emails start with a "Subject:" line.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FAIL = "FAIL"
CHECK = "CHECK"

GUIDE_MAX_WORDS = 450
READING_GRADE_MAX = 10.0
LONG_SENTENCE_WORDS = 30
SUBJECT_MAX_CHARS = 60
PLACEHOLDER_DISCLAIMER = "[PLACEHOLDER DISCLAIMER]"


@dataclass(frozen=True)
class Rule:
    level: str
    section: str
    message: str
    pattern: re.Pattern


def _rule(level: str, section: str, message: str, pattern: str) -> Rule:
    return Rule(level, section, message, re.compile(pattern, re.IGNORECASE))


# Wording rules, checked line by line. Sections match the checklist.
RULES = [
    # A. General information, not advice.
    _rule(
        FAIL,
        "A",
        "Reads as advice. Rephrase as general information.",
        r"\byou (?:should|must|ought to)\b"
        r"(?!\s+(?:speak|talk|check|ask|seek|get (?:independent |your own )?advice))"
        r"|\bwe (?:recommend|suggest|advise)\b|\bI (?:recommend|suggest|advise)\b"
        r"|\b(?:best|right|smartest|ideal) (?:option|choice|loan|lender|time|move)\b",
    ),
    _rule(
        CHECK,
        "A",
        "May read as an instruction. Confirm it is general process, not advice.",
        r"\byou(?:'ll| will)? need to\b|\bmake sure you\b",
    ),
    _rule(
        FAIL,
        "A",
        "Promised or implied outcome. Remove it.",
        r"\bguarantee[sd]?\b|\brisk[- ]free\b|\bno risk\b|\bwill save\b"
        r"|\b(?:easy|fast|quick|instant) approval\b|\bapproved in\b|\bcan't lose\b",
    ),
    _rule(
        CHECK,
        "A",
        "Possible implied outcome. Confirm it promises nothing.",
        r"\bsave (?:thousands|money|you)\b|\bget approved\b"
        r"|\bpay (?:off|down) (?:your|the) loan faster\b",
    ),
    _rule(
        FAIL,
        "A",
        "Pressure or urgency. Remove it.",
        r"\bact now\b|\blimited time\b|\bdon'?t miss\b|\bhurry\b|\blast chance\b"
        r"|\btoday only\b|\bbefore it'?s too late\b|\bspots? (?:are )?filling\b",
    ),
    _rule(
        FAIL,
        "A",
        "Interest rate or repayment figure. Rates are out of scope.",
        r"\d[\d.,]*\s*(?:%|per ?cent)[^.]*\b(?:interest|rate|p\.a\.|comparison)\b"
        r"|\b(?:interest|comparison) rates? (?:of|from|at|is|are)\s*\d"
        r"|\bp\.a\.|\brepayments? of \$",
    ),
    _rule(
        CHECK,
        "A",
        "Mentions rates. Confirm no figure, comparison, or prediction.",
        r"\binterest rates?\b|\bcomparison rates?\b",
    ),
    # B. Accuracy: figures need a recorded source.
    _rule(
        CHECK,
        "B",
        "Figure. Record its official source and date in the source log.",
        r"\$\s?\d[\d,.]*\s*(?:k|m|million|thousand)?|\b\d[\d.,]*\s*(?:%|per ?cent)",
    ),
    # C. Honest subject lines and emphasis.
    _rule(FAIL, "C", "Repeated exclamation marks. Remove them.", r"!{2,}"),
    # D. Fairness and inclusion.
    _rule(
        FAIL,
        "D",
        "Gendered wording. Use 'you', 'they', or 'your partner or co-buyer'.",
        r"\b(?:he|she|him|his|her|hers|himself|herself|husband|wife|boyfriend|girlfriend"
        r"|guys|ladies|gentlemen|chairman|manpower)\b",
    ),
    _rule(
        FAIL,
        "D",
        "Assumes age. Remove it, as first-home buyers and investors can be any age.",
        r"\b(?:young|younger|older|elderly|millennials?|boomers?|gen ?z|retirees?"
        r"|twenty-?somethings?)\b|\bin your (?:20|30|40|50|60)s\b",
    ),
    _rule(
        FAIL,
        "D",
        "Assumes a family or relationship. Use 'your partner or co-buyer' or remove it.",
        r"\byour (?:spouse|kids|children|family)\b|\bstart(?:ing)? a family\b"
        r"|\bmarried couples?\b",
    ),
    _rule(
        FAIL,
        "D",
        "Stereotype about income. Remove it.",
        r"\b(?:wealthy|high[- ]earning|high[- ]income|well[- ]paid|rich)\b"
        r"|\b(?:doctors|dentists|nurses|pharmacists|physios?) (?:earn|are paid|make)\b",
    ),
    # F. Privacy.
    _rule(
        FAIL,
        "F",
        "Mobile number. Use the business's published number only.",
        r"(?:\+?61[\s-]?|\b0)4(?:[\s-]?\d){8}\b",
    ),
    # H. Links shown in full, never shortened.
    _rule(
        FAIL,
        "H",
        "Shortened link. Show the full link instead.",
        r"\b(?:bit\.ly|tinyurl\.com|t\.co|goo\.gl|ow\.ly|buff\.ly|rebrand\.ly|cutt\.ly"
        r"|shorturl\.at|lnkd\.in|tiny\.cc|is\.gd)/",
    ),
    _rule(FAIL, "H", "Link is not https. Use the https address.", r"\bhttp://"),
    _rule(
        FAIL,
        "H",
        "Hidden link text. Show the full link, not 'click here' or other words.",
        r"\[(?!https://)[^\]]+\]\(https?://[^)]+\)|\bclick here\b",
    ),
    _rule(
        FAIL,
        "H",
        "Placeholder or note left in the draft. Replace it before review.",
        r"\bTODO\b|\bTBC\b|\[X+\]|\bX{2,}\b|\[insert[^\]]*\]",
    ),
]

# All-caps words that are fine.
ACRONYMS = set(
    """
    ACL AHPRA ASIC ATO CDBS DVA FHOG FHSS GP GPS LMI LVR NDIS PDF QR SMSF SMSFS WA HICAPS
    HBF ABN TFN PAYG GST IVF FAQ OK AM PM
    """.split()
)
# Terms that should be explained the first time they are used.
JARGON = {
    "LMI": "lenders mortgage insurance",
    "LVR": "loan-to-value ratio",
    "SMSF": "self-managed super fund",
    "FHOG": "first home owner grant",
    "FHSS": "first home super saver",
    "offset account": "offset account is",
    "negative gearing": "negative gearing is",
    "equity": "equity is",
}
OPT_OUT = re.compile(
    r"\bunsubscribe\b|\bopt[- ]out\b|\bprefer not to (?:hear|receive)\b"
    r"|\bdon'?t (?:want|wish) to (?:hear|receive)\b|\blet me know and I won'?t\b",
    re.IGNORECASE,
)
ADVISER = re.compile(r"\baccountant\b|\b(?:licensed|financial|tax) adviser\b", re.IGNORECASE)
FULL_LINK = re.compile(r"https://\S+")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


@dataclass(frozen=True)
class Finding:
    level: str
    section: str
    line: int
    message: str
    excerpt: str = ""


@dataclass(frozen=True)
class DraftKind:
    kind: str
    number: int | None
    complex_topic: bool


def kind_of(path: Path) -> DraftKind:
    name = path.stem.lower()
    complex_topic = "complex" in name
    email = re.search(r"email-?(\d+)", name)
    if email:
        return DraftKind("email", int(email.group(1)), complex_topic)
    for kind in ("guide", "invitation"):
        if kind in name:
            return DraftKind(kind, None, complex_topic)
    if "slide" in name or "presentation" in name:
        return DraftKind("slides", None, complex_topic)
    return DraftKind("other", None, complex_topic)


def _syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and not word.endswith(("le", "ee")) and count > 1:
        count -= 1
    return max(count, 1)


def reading_grade(text: str) -> float:
    """Flesch-Kincaid grade level, a rough guide to reading difficulty."""
    sentences = [s for s in re.split(r"[.!?]+\s|\n{2,}", text) if WORD.search(s)]
    words = WORD.findall(text)
    if not sentences or not words:
        return 0.0
    syllables = sum(_syllables(word) for word in words)
    return 0.39 * len(words) / len(sentences) + 11.8 * syllables / len(words) - 15.59


def _prose(text: str) -> str:
    """Text without links, headings markup, or the Subject line, for reading measures."""
    text = re.sub(r"^Subject:.*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
    text = FULL_LINK.sub("", text)
    return re.sub(r"^[#>*\-\s]+", "", text, flags=re.MULTILINE)


def check_draft(text: str, path: Path, disclaimer: str | None = None) -> list[Finding]:
    """Check one draft and return its findings."""
    kind = kind_of(path)
    findings: list[Finding] = []
    lines = text.splitlines()

    # The disclaimer itself may contain advice-like wording, so it is not scanned.
    disclaimer_lines = set()
    for number, line in enumerate(lines, start=1):
        if line.strip().lower().startswith("disclaimer") or (
            disclaimer and line.strip() and line.strip() in disclaimer
        ):
            disclaimer_lines.add(number)

    for number, line in enumerate(lines, start=1):
        if number in disclaimer_lines:
            continue
        for rule in RULES:
            for match in rule.pattern.finditer(line):
                findings.append(
                    Finding(rule.level, rule.section, number, rule.message, match.group(0))
                )
        for word in re.findall(r"\b[A-Z]{4,}\b", line):
            if word not in ACRONYMS:
                findings.append(
                    Finding(CHECK, "C", number, "ALL CAPS word. Use normal case.", word)
                )

    findings += _structure_findings(text, lines, kind, disclaimer)
    return sorted(findings, key=lambda f: (f.line, f.level != FAIL, f.section))


def _structure_findings(
    text: str, lines: list[str], kind: DraftKind, disclaimer: str | None
) -> list[Finding]:
    findings = []
    lowered = text.lower()

    if PLACEHOLDER_DISCLAIMER.lower() in lowered:
        findings.append(
            Finding(CHECK, "A", 0, "Placeholder disclaimer. Replace it with the real one.")
        )
    elif disclaimer and " ".join(disclaimer.split()).lower() not in " ".join(lowered.split()):
        findings.append(Finding(FAIL, "A", 0, "The business's disclaimer is missing or altered."))
    elif not disclaimer and not any(
        line.strip().lower().startswith("disclaimer") for line in lines
    ):
        findings.append(Finding(FAIL, "A", 0, "No disclaimer found."))

    if kind.complex_topic and not ADVISER.search(text):
        findings.append(
            Finding(
                FAIL, "A", 0, "Complex structures content must refer to an accountant or adviser."
            )
        )

    if kind.kind == "email":
        subject = next((line for line in lines if line.strip()), "")
        if not subject.lower().startswith("subject:"):
            findings.append(Finding(FAIL, "C", 1, "Emails must start with a 'Subject:' line."))
        else:
            value = subject.split(":", 1)[1].strip()
            if re.match(r"(?:re|fwd?)\s*:", value, re.IGNORECASE):
                findings.append(Finding(FAIL, "C", 1, "Subject pretends to be a reply or forward."))
            if len(value) > SUBJECT_MAX_CHARS:
                findings.append(Finding(CHECK, "C", 1, "Subject is long and may be cut off."))
        if not re.search(r"\bunsubscribe\b", text, re.IGNORECASE):
            findings.append(Finding(FAIL, "C", 0, "Sequence emails need an unsubscribe link."))
        # The unsubscribe link does not count as the link to the guide.
        guide_links = [
            line for line in lines if FULL_LINK.search(line) and "unsubscribe" not in line.lower()
        ]
        if kind.number == 1 and not guide_links:
            findings.append(
                Finding(FAIL, "C", 0, "The first email must link to the guide, shown in full.")
            )

    if kind.kind == "invitation" and not OPT_OUT.search(text):
        findings.append(Finding(FAIL, "C", 0, "The invitation needs a way to opt out."))

    prose = _prose(text)
    words = WORD.findall(prose)
    if kind.kind == "guide" and len(words) > GUIDE_MAX_WORDS:
        findings.append(
            Finding(CHECK, "E", 0, f"{len(words)} words, which may not fit on one page.")
        )
    if kind.kind in {"guide", "email", "invitation"}:
        grade = reading_grade(prose)
        if grade > READING_GRADE_MAX:
            findings.append(
                Finding(CHECK, "D", 0, f"Reading level about Year {grade:.0f}. Aim for Year 9.")
            )
        for sentence in re.split(r"(?<=[.!?])\s+", prose):
            if len(WORD.findall(sentence)) > LONG_SENTENCE_WORDS:
                findings.append(
                    Finding(CHECK, "D", 0, "Long sentence. Consider splitting it.", sentence[:40])
                )
    for term, explanation in JARGON.items():
        if re.search(rf"\b{re.escape(term)}\b", text) and explanation.lower() not in lowered:
            findings.append(Finding(CHECK, "D", 0, "Term may need explaining.", term))
    return findings


def check_paths(paths: list[Path], disclaimer: str | None = None) -> dict[Path, list[Finding]]:
    files = []
    for path in paths:
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if p.suffix.lower() in {".md", ".txt"})
        else:
            files.append(path)
    return {file: check_draft(file.read_text(), file, disclaimer) for file in files}


def _format(finding: Finding) -> str:
    where = f"line {finding.line}" if finding.line else "whole draft"
    excerpt = f' "{finding.excerpt}"' if finding.excerpt else ""
    return f"  {finding.level:<5} {finding.section}  {where}:{excerpt} {finding.message}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="content-check",
        description="First automated pass over content drafts before human review.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Draft files or folders.")
    parser.add_argument(
        "--disclaimer-file", type=Path, help="File holding the exact disclaimer text."
    )
    args = parser.parse_args(argv)
    disclaimer = args.disclaimer_file.read_text().strip() if args.disclaimer_file else None

    results = check_paths(args.paths, disclaimer)
    if not results:
        print("No .md or .txt drafts found.")
        return 1

    clean = checks_only = failed = fails = checks = 0
    for path, findings in results.items():
        kind = kind_of(path)
        label = kind.kind + (f" {kind.number}" if kind.number else "")
        print(f"{path.name} ({label})")
        if not findings:
            print("  PASS  no issues found")
        for finding in findings:
            print(_format(finding))
        file_fails = sum(f.level == FAIL for f in findings)
        fails += file_fails
        checks += len(findings) - file_fails
        if file_fails:
            failed += 1
        elif findings:
            checks_only += 1
        else:
            clean += 1
        print()

    print(
        f"{len(results)} drafts: {clean} clean, {checks_only} with checks only, "
        f"{failed} with failures ({fails} FAIL, {checks} CHECK)."
    )
    print("A clean result means ready for human review, not approved.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
