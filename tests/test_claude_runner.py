import json
import subprocess

import pytest

from org_research_agent import claude_runner
from org_research_agent.claude_runner import ClaudeError, build_command, run_claude


class FakeCompleted:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def patch_run(monkeypatch, stdout, returncode=0):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return FakeCompleted(stdout, returncode)

    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)
    return calls


def test_command_is_locked_down():
    command = build_command("hello")
    assert command[:3] == ["claude", "-p", "hello"]
    assert "--restricted" in command
    assert "--no-session-persistence" in command
    assert "--strict-mcp-config" in command
    # Only WebFetch is offered as a tool.
    assert command[command.index("--tools") + 1] == "WebFetch"
    assert command[command.index("--allowedTools") + 1] == "WebFetch"


def test_returns_text_and_cost(monkeypatch):
    calls = patch_run(monkeypatch, json.dumps({"result": "OK", "total_cost_usd": 0.01}))
    result = run_claude("hi")
    assert result.text == "OK"
    assert result.cost_usd == 0.01
    # It must run in a temporary folder, not the current one.
    assert calls[0][1]["cwd"] != "."


def test_error_flag_raises(monkeypatch):
    patch_run(monkeypatch, json.dumps({"is_error": True, "subtype": "error_max_budget_usd"}), 1)
    with pytest.raises(ClaudeError, match="error_max_budget_usd"):
        run_claude("hi")


def test_bad_json_raises(monkeypatch):
    patch_run(monkeypatch, "not json")
    with pytest.raises(ClaudeError, match="valid JSON"):
        run_claude("hi")


def test_timeout_raises(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)
    with pytest.raises(ClaudeError, match="timed out"):
        run_claude("hi", timeout_s=1)


def test_missing_claude_command_raises(monkeypatch):
    def fake_run(command, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)
    with pytest.raises(ClaudeError, match="not found"):
        run_claude("hi")
