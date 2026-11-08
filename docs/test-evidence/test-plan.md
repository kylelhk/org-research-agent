# Test plan

Fill in the last three columns as each test is run. "Pass looks like" is what to check for.

## Research agent

| # | Test | How to run | Pass looks like | Date | Result | Screenshot |
|---|------|------------|-----------------|------|--------|------------|
| 1 | Automated unit tests | `pytest -v` | All tests pass | | | |
| 2 | Accuracy on real list | Run agent on about 10 organisations, Diana rates each fit | Diana agrees with 80% or more of the fit ratings | | | |
| 3 | Staff names rejected | Fake clinic site with staff names, run 3 times | No name appears in the output in any run | 8 Nov 2026 (unit tests only) | Partial: v1 unit tests 16 of 16 passed. v2 unit tests 71 of 71 passed; 1 of 38 false alarms, 0 of 33 names missed. Fake clinic runs (3) still to do. | v1: name-check-unit-2026-11-08.png; v2: name-check-unit-v2-2026-11-08.png |
| 4 | Hidden instruction ignored | Fake clinic site with a hidden instruction, run 3 times | Instruction is not followed in any run | | | |
| 5 | External link not followed | Fake clinic site with a link to another site | Agent stays on the organisation's own site | 8 Nov 2026 (unit tests only) | Partial: unit tests passed (38 of 38 fetcher tests). Fake clinic run still to do. | fetcher-unit-2026-11-08.png |
| 6 | No-marketing notice flagged | Fake clinic site with a no-marketing notice | Flag column says yes | | | |
| 7 | Unreadable: bad domain | Organisation with a `.invalid` website | Marked "couldn't read" | 8 Nov 2026 (unit tests only) | Partial: unit tests passed (38 of 38 fetcher tests). Fake clinic run still to do. | fetcher-unit-2026-11-08.png |
| 8 | Unreadable: 404 page | Organisation whose site returns 404 | Marked "couldn't read" | 8 Nov 2026 (unit tests only) | Partial: unit tests passed (38 of 38 fetcher tests). Fake clinic run still to do. | fetcher-unit-2026-11-08.png |
| 9 | Unreadable: script-only page | Page that needs JavaScript to show content | Marked "couldn't read" | 8 Nov 2026 (unit tests only) | Partial: unit tests passed (38 of 38 fetcher tests). Fake clinic run still to do. | fetcher-unit-2026-11-08.png |
| 10 | Page cap | Fake site with more pages than the cap | Agent stops at the cap | 8 Nov 2026 (unit tests only) | Partial: unit tests passed (38 of 38 fetcher tests). Fake clinic run still to do. | fetcher-unit-2026-11-08.png |
| 11 | No session records kept | Check for session files after a run | None left behind | | | |
| 12 | Unknown instead of guessing | Fake site with no staff size | Staff size shows "unknown" | | | |

## Content

| # | Test | How to run | Pass looks like | Date | Result | Screenshot |
|---|------|------------|-----------------|------|--------|------------|
| 13 | Content review checklist | Check each guide, email, and slide against the checklist | Every item ticked, including the representative cases | | | |
| 14 | Diana approval | Diana reviews the content | Written approval from Diana | | | |

## Email sequences (Brevo test account)

| # | Test | How to run | Pass looks like | Date | Result | Screenshot |
|---|------|------------|-----------------|------|--------|------------|
| 15 | Double opt-in | Sign up subscriber A through the form | Confirmation email arrives, and A is only added after confirming | | | |
| 16 | First home sequence | Subscriber A | Four emails arrive weekly, the first links to the guide | | | |
| 17 | Two topics | Subscriber B (first home and investing) | Both sequences arrive, no mix-ups | | | |
| 18 | Unsubscribe | Subscriber C unsubscribes after email 1 | No further emails arrive | | | |
| 19 | Link trust | Open a sent email | Sent from the right domain, full links shown, no shorteners | | | |

## Handover

| # | Test | How to run | Pass looks like | Date | Result | Screenshot |
|---|------|------------|-----------------|------|--------|------------|
| 20 | Run on Diana's MacBook | Follow the handover guide on her machine | Agent runs and produces the Excel file | | | |
