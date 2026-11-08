"""Run Claude Code non-interactively with only web fetching allowed.

Every call runs in a fresh empty folder, with no saved session, no extra
tools, no MCP servers, and no user, project, or local settings files.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass

DEFAULT_TIMEOUT_S = 180
DEFAULT_MAX_BUDGET_USD = 0.50


class ClaudeError(Exception):
    """Raised when a Claude Code call fails or returns an error."""


@dataclass(frozen=True)
class ClaudeResult:
    text: str
    cost_usd: float


def build_command(prompt: str, max_budget_usd: float = DEFAULT_MAX_BUDGET_USD) -> list[str]:
    """Build the locked-down command line for one call."""
    return [
        "claude",
        "-p",
        prompt,
        "--restricted",
        "--tools",
        "WebFetch",
        "--allowedTools",
        "WebFetch",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--permission-prompts",
        "none",
        "--max-budget-usd",
        str(max_budget_usd),
        "--output-format",
        "json",
    ]


def run_claude(
    prompt: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    max_budget_usd: float = DEFAULT_MAX_BUDGET_USD,
) -> ClaudeResult:
    """Send one prompt to Claude Code and return its reply."""
    command = build_command(prompt, max_budget_usd)
    # An empty temporary folder means there is nothing local for Claude to find.
    with tempfile.TemporaryDirectory() as workdir:
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

    return ClaudeResult(text=data.get("result", ""), cost_usd=data.get("total_cost_usd", 0.0))
