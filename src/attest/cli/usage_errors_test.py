"""Usage errors, raised before a command body runs, print the JSON error envelope."""

import json
import re

import pytest
from typer.testing import CliRunner

from attest.cli import app

runner = CliRunner(env={"COLUMNS": "200", "TERMINAL_WIDTH": "200"})


def _invalid_input(args: list[str]) -> dict:
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "2"
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"
    return payload


@pytest.fixture
def trajectory(tmp_path) -> str:
    path = tmp_path / "trajectory.json"
    path.write_text(json.dumps({"task": "t", "steps": [], "final_answer": "a"}))
    return str(path)


@pytest.mark.parametrize(
    ("command", "option"),
    [("run", "--max-claims"), ("run", "--max-calls"), ("run", "--max-tokens")],
)
def test_a_bad_int_option_on_run_is_invalid_input(trajectory, command, option):
    payload = _invalid_input([command, trajectory, option, "abc"])
    assert payload["command"] == command
    assert option in payload["error"]["message"]
    assert "'abc'" in payload["error"]["message"]


def test_a_bad_int_option_on_review_is_invalid_input(trajectory):
    payload = _invalid_input(["review", trajectory, "--max-claims", "abc"])
    assert payload["command"] == "review"
    assert "--max-claims" in payload["error"]["message"]


@pytest.mark.parametrize("command", ["run", "tools", "injection", "role", "review"])
def test_an_unknown_option_is_invalid_input(trajectory, command):
    payload = _invalid_input([command, trajectory, "--bogus"])
    assert payload["command"] == command
    assert "--bogus" in payload["error"]["message"]


def test_a_missing_argument_is_invalid_input():
    payload = _invalid_input(["tools"])
    assert payload["command"] == "tools"
    assert "Missing argument" in payload["error"]["message"]


@pytest.mark.parametrize("args", [["bogus"], ["--bogus"], []])
def test_a_missing_or_unknown_command_is_invalid_input(args):
    assert _invalid_input(args)["command"] == "attest"


def test_help_still_prints_help():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--max-claims" in re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
