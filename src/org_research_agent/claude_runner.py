"""Run Claude Code non-interactively with one tool: our own fetch_page.

Every call runs in a fresh empty folder, with no saved session, no built-in
tools, no MCP servers except ours, and no user, project, or local settings
files. All fetching goes through fetch_page, which enforces the rules.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from org_research_agent.fetch_server import QUALIFIED_TOOL_NAME, SERVER_NAME

DEFAULT_TIMEOUT_S = 300
DEFAULT_MAX_BUDGET_USD = 0.50


class ClaudeError(Exception):
    """Raised when a Claude Code call fails or returns an error."""


@dataclass(frozen=True)
class ClaudeResult:
    text: str
    cost_usd: float
    # The parsed answer when a JSON schema was given, otherwise None.
    structured: dict | None = None


def build_mcp_config(
    host: str,
    max_pages: int,
    fetch_log: Path,
    evidence_path: Path | None = None,
    allowed_terms: tuple[str, ...] = (),
) -> dict:
    """The MCP config that starts our fetch server for one organisation."""
    args = [
        "-m",
        "org_research_agent.fetch_server",
        "--host",
        host,
        "--max-pages",
        str(max_pages),
        "--log",
        str(fetch_log.resolve()),
    ]
    if evidence_path:
        args += ["--evidence", str(evidence_path.resolve())]
    for term in allowed_terms:
        args += ["--allowed-term", term]
    return {"mcpServers": {SERVER_NAME: {"command": sys.executable, "args": args}}}


def build_command(
    prompt: str,
    mcp_config_path: Path,
    max_budget_usd: float = DEFAULT_MAX_BUDGET_USD,
    json_schema: dict | None = None,
) -> list[str]:
    """Build the locked-down command line for one call."""
    schema_args = ["--json-schema", json.dumps(json_schema)] if json_schema else []
    return [
        "claude",
        "-p",
        prompt,
        "--restricted",
        # No built-in tools at all, so no WebFetch, shell, or file access.
        "--tools",
        "",
        "--mcp-config",
        str(mcp_config_path),
        "--strict-mcp-config",
        "--allowedTools",
        QUALIFIED_TOOL_NAME,
        "--disable-slash-commands",
        "--no-session-persistence",
        "--permission-prompts",
        "none",
        "--max-budget-usd",
        str(max_budget_usd),
        "--output-format",
        "json",
        *schema_args,
    ]


def run_claude(
    prompt: str,
    host: str,
    max_pages: int,
    fetch_log: Path | str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    max_budget_usd: float = DEFAULT_MAX_BUDGET_USD,
    json_schema: dict | None = None,
    evidence_path: Path | str | None = None,
    allowed_terms: tuple[str, ...] = (),
) -> ClaudeResult:
    """Send one prompt to Claude Code, letting it read only the given website."""
    # An empty temporary folder means there is nothing local for Claude to find.
    with tempfile.TemporaryDirectory() as workdir:
        config_path = Path(workdir) / "mcp.json"
        config = build_mcp_config(
            host,
            max_pages,
            Path(fetch_log),
            Path(evidence_path) if evidence_path else None,
            allowed_terms,
        )
        config_path.write_text(json.dumps(config))
        command = build_command(prompt, config_path, max_budget_usd, json_schema)
        try:
            completed = subprocess.run(
                command, cwd=workdir, capture_output=True, text=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired as error:
            raise ClaudeError(f"Claude Code timed out after {timeout_s} seconds.") from error
        except FileNotFoundError as error:
            raise ClaudeError("The 'claude' command was not found. Is it installed?") from error

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ClaudeError(
            f"Claude Code did not return valid JSON (exit code {completed.returncode})."
        ) from error

    if completed.returncode != 0 or data.get("is_error"):
        raise ClaudeError(f"Claude Code reported an error: {data.get('subtype', 'unknown')}.")

    return ClaudeResult(
        text=data.get("result", ""),
        cost_usd=data.get("total_cost_usd", 0.0),
        structured=data.get("structured_output"),
    )
