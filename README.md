# Org Research Agent

A Python program that uses Claude Code in non-interactive mode (`claude -p`) to screen local organisations for fit, with privacy safeguards built in. It is built as part of the Victoria Park AI Business Boost program.

> Status: early build. This repository holds general-purpose code only. Client criteria, prompts, and any outputs stay in git-ignored private files.

## Design goals

- Read each organisation's own website only, with a page cap, and respect robots.txt and terms.
- Take staff size only from a number the website states, such as "our team of eight". Team and staff pages are never passed to the agent, because they list staff by name. Any output containing a name is rejected.
- Mark "unknown" or "couldn't read" instead of guessing.
- Give Claude Code one tool only, a custom `fetch_page` MCP tool, instead of the built-in web fetch. The agent chooses which pages to read, but the tool enforces the rules in code: own website only, robots.txt, a page cap, and no team or staff pages. A team page is caught from its address before it is opened, or from its title or main heading after download, when its text is dropped on this computer. Every request is logged without page content.
- Keep no session records.
- Write results to an Excel file for a human to review.

## Setup

Requires Python 3.11 or newer. The virtual environment lives outside the synced project folder to avoid syncing thousands of files.

```bash
python3 -m venv ~/.venvs/org-research-agent
source ~/.venvs/org-research-agent/bin/activate
pip install -e ".[dev]"
pytest
```

## Private settings

```bash
cp config/settings.example.toml config/settings.private.toml
```

Edit the private copy. It is listed in `.gitignore` and must never be committed.

## Running

```bash
org-research --dry-run      # List the organisations without researching them
org-research --limit 3      # Research the first 3 only
org-research                # Research the full list
```

Results are saved to `output/research-<date>.xlsx`, with a status column for the reviewer. Each request the agent makes is logged to `runs/<date>/fetch-log.jsonl`, without page content. Both folders are git-ignored. Press Ctrl+C to stop; finished organisations are still saved.

After each organisation, the run reads the new lines of the fetch log. If the agent asked for another website, a staff profile page, or a page robots.txt forbids, the request was refused and the organisation's row says so in the Notes column. The run summary shows the totals.

Each Excel file also has a **Run info** sheet with the agent's time per organisation, and columns for the reviewer's checking and rework time. Once those are filled in, compare with a baseline:

```bash
baseline-report output/research-<date>.xlsx --baseline-min <baseline minutes per organisation>
```

The method is in [`docs/baseline-comparison-method.docx`](docs/baseline-comparison-method.docx). Known limits and readiness are in [`docs/limitations-and-readiness.docx`](docs/limitations-and-readiness.docx).

## Content tools

```bash
content-pack private/content/first-home --title "First home" --draft 1   # Build a Word review pack from drafts
content-check private/content/first-home                                  # First automated pass, Word packs included
```

A review pack holds the content from one folder, with its source log and a sign-off table. To keep the review short, all the content (guides, emails, invitation, and slides) goes into one pack, which the consultant and the business owner review together in one session, editing in Word with Track Changes. `content-check` reads the pack directly once changes are accepted. A clean result means ready for human review, not approved. The full review steps are in [`docs/content-review-checklist.docx`](docs/content-review-checklist.docx).

## Project layout

```text
src/org_research_agent/   Package source
tests/                    Automated tests
config/                   Example settings (private copy is git-ignored)
```
