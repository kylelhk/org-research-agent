import json
import subprocess
from pathlib import Path

import pytest

from org_research_agent import claude_runner
from org_research_agent.claude_runner import (
    ClaudeError,
    build_command,
    build_mcp_config,
    run_claude,
)


class FakeCompleted:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def patch_run(monkeypatch, stdout, returncode=0):
    calls = []

    def fake_run(command, **kwargs):
        # Read the MCP config while the temp folder still exists.
        config_path = Path(command[command.index("--mcp-config") + 1])
        calls.append((command, kwargs, json.loads(config_path.read_text())))
        return FakeCompleted(stdout, returncode)

    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)
    return calls


def test_command_allows_only_our_fetch_tool(tmp_path):
    command = build_command("hello", tmp_path / "mcp.json")
    assert command[:3] == ["claude", "-p", "hello"]
    for flag in (
        "--restricted",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--disable-slash-commands",
    ):
        assert flag in command
    # Built-in tools are switched off entirely.
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--allowedTools") + 1] == "mcp__fetcher__fetch_page"


def test_mcp_config_passes_site_cap_and_log(tmp_path):
    config = build_mcp_config("clinic.test", 4, tmp_path / "log.jsonl")
    args = config["mcpServers"]["fetcher"]["args"]
    assert args[args.index("--host") + 1] == "clinic.test"
    assert args[args.index("--max-pages") + 1] == "4"
    assert args[args.index("--log") + 1] == str((tmp_path / "log.jsonl").resolve())


def test_returns_text_and_cost(monkeypatch, tmp_path):
    calls = patch_run(monkeypatch, json.dumps({"result": "OK", "total_cost_usd": 0.01}))
    result = run_claude("hi", "clinic.test", 4, tmp_path / "log.jsonl")
    assert result.text == "OK"
    assert result.cost_usd == 0.01
    command, kwargs, config = calls[0]
    assert kwargs["cwd"] != "."
    assert "fetcher" in config["mcpServers"]


def test_error_flag_raises(monkeypatch, tmp_path):
    patch_run(monkeypatch, json.dumps({"is_error": True, "subtype": "error_max_budget_usd"}), 1)
    with pytest.raises(ClaudeError, match="error_max_budget_usd"):
        run_claude("hi", "clinic.test", 4, tmp_path / "log.jsonl")


def test_bad_json_raises(monkeypatch, tmp_path):
    patch_run(monkeypatch, "not json")
    with pytest.raises(ClaudeError, match="valid JSON"):
        run_claude("hi", "clinic.test", 4, tmp_path / "log.jsonl")


def test_timeout_raises(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)
    with pytest.raises(ClaudeError, match="timed out"):
        run_claude("hi", "clinic.test", 4, tmp_path / "log.jsonl", timeout_s=1)


def test_missing_claude_command_raises(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)
    with pytest.raises(ClaudeError, match="not found"):
        run_claude("hi", "clinic.test", 4, tmp_path / "log.jsonl")
