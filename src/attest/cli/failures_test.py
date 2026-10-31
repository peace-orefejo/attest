"""CLI behaviour on unreadable input and failing judge calls: always a JSON envelope."""

import json
import sys

from typer.testing import CliRunner

from attest import Attest
from attest.cli import app
from attest.llm import using

runner = CliRunner(env={"COLUMNS": "200", "TERMINAL_WIDTH": "200"})

RUN = {
    "task": "capital?",
    "system_prompt": "Geography only.",
    "steps": [{"tool_call": {"name": "search", "output": "Paris\u0000\u001b[31m‮"}}],
    "final_answer": "Paris.",
}


class _TimingOut:
    def create(self, **kwargs):
        raise TimeoutError("the request timed out")


def _file(tmp_path, content: bytes, name="run.json"):
    path = tmp_path / name
    path.write_bytes(content)
    return str(path)


def _payload(result) -> dict:
    return json.loads(result.stdout)


def test_a_trajectory_file_that_is_not_utf8_is_invalid_input(tmp_path):
    result = runner.invoke(app, ["tools", _file(tmp_path, b'{"task": "\xff\xfe"}')])
    assert result.exit_code == 2
    error = _payload(result)["error"]
    assert error["code"] == "invalid_input"
    assert "Could not read trajectory file" in error["message"]


def test_a_review_file_that_is_not_utf8_is_invalid_input(tmp_path):
    result = runner.invoke(app, ["review", _file(tmp_path, b"\xff\xfe{}")])
    assert result.exit_code == 2
    assert _payload(result)["error"]["code"] == "invalid_input"


def test_control_characters_in_tool_output_still_print_valid_json(tmp_path):
    result = runner.invoke(app, ["tools", _file(tmp_path, json.dumps(RUN).encode())])
    assert result.exit_code == 0
    assert _payload(result)["data"]["trajectories"][0]["result"]["passed"] is True


def test_a_failing_role_judge_prints_an_unchecked_result(tmp_path, monkeypatch):
    module = sys.modules["attest.cli.commands.role"]
    monkeypatch.setattr("attest.cli.context.resolve_key", lambda provider: "sk-test")
    monkeypatch.setattr(module, "llm_context", lambda provider, model: using(_TimingOut()))
    result = runner.invoke(app, ["role", _file(tmp_path, json.dumps(RUN).encode())])
    assert result.exit_code == 0
    finding = _payload(result)["data"]["trajectories"][0]["result"]["findings"][0]
    assert finding["verdict"] == "unchecked"
    assert "TimeoutError" in finding["reason"]


def test_an_error_no_check_absorbs_is_a_json_command_failure(tmp_path, monkeypatch):
    def fail(self, pr, outputs, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(Attest, "review", fail)
    monkeypatch.setattr("attest.cli.context.resolve_key", lambda provider: "sk-test")
    review_file = {"pr": {"diffs": {"a.py": "+x = 1\n"}}, "outputs": []}
    result = runner.invoke(app, ["review", _file(tmp_path, json.dumps(review_file).encode())])
    assert result.exit_code == 1
    payload = _payload(result)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "command_failed"
    assert "RuntimeError: provider unavailable" in payload["error"]["message"]


class _KeyRejected(Exception):
    status_code = 401


class _Rejected:
    def create(self, **kwargs):
        raise _KeyRejected("Error code: 401 - {'error': 'invalid x-api-key sk-ant-SECRET'}")


def test_a_rejected_api_key_is_a_json_provider_config_error(tmp_path, monkeypatch):
    module = sys.modules["attest.cli.commands.role"]
    monkeypatch.setattr("attest.cli.context.resolve_key", lambda provider: "sk-test")
    monkeypatch.setattr(module, "llm_context", lambda provider, model: using(_Rejected()))
    result = runner.invoke(app, ["role", _file(tmp_path, json.dumps(RUN).encode())])
    assert result.exit_code == 1
    error = _payload(result)["error"]
    assert error["code"] == "provider_config"
    assert "401" in error["message"]
    assert "SECRET" not in result.stdout
