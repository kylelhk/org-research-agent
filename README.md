# Org Research Agent

A Python program that uses Claude Code in non-interactive mode (`claude -p`) to screen local organisations for fit, with privacy safeguards built in. It is built as part of the Victoria Park AI Business Boost program.

> Status: early build. This repository holds general-purpose code only. Client criteria, prompts, and any outputs stay in git-ignored private files.

## Design goals

- Read each organisation's own website only, with a page cap, and respect robots.txt and terms.
- Count staff without storing personal information: any output containing a name is rejected.
- Mark "unknown" or "couldn't read" instead of guessing.
- Give Claude Code one tool only, a custom `fetch_page` MCP tool. The agent chooses which pages to read, but the tool enforces the rules in code: own website only, robots.txt, a page cap, and no staff profile pages. Every request is logged without page content.
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

## Project layout

```text
src/org_research_agent/   Package source
tests/                    Automated tests
config/                   Example settings (private copy is git-ignored)
```
