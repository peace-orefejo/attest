"""`Attest(reasoning=...)` and `--reasoning`: the level reaches each call and is recorded."""

import json
import sys
import types

import pytest
from typer.testing import CliRunner

from attest import Attest, ReasoningPolicy
from attest.checks.verify import VerdictOut
from attest.cli import app
from attest.llm.anthropic_client import AnthropicClient
from attest.trajectory import Step, ToolCall, Trajectory

COMMANDS = ("run", "review", "role", "injection", "tools", "demo")
runner = CliRunner(env={"COLUMNS": "200", "TERMINAL_WIDTH": "200"})

RUN = Trajectory(
    task="Capital of France?",
    system_prompt="You answer geography questions only.",
    steps=[Step(tool_call=ToolCall(name="search", output="Paris is the capital."))],
    final_answer="Paris is the capital.",
)


class _Messages:
    def __init__(self):
        self.efforts: dict[str, str] = {}

    def parse(self, **kwargs):
        self.efforts[kwargs["output_format"].__name__] = kwargs["output_config"]["effort"]
        answer = VerdictOut(verdict="supported")
        model = kwargs["output_format"]
        parsed = (
            model(claims=["Paris is the capital."]) if model.__name__ == "ClaimsOut" else answer
        )
        if model.__name__ == "_RoleOut":
            parsed = model(verdict="in_scope")
        usage = types.SimpleNamespace(input_tokens=1, output_tokens=1)
        return types.SimpleNamespace(parsed_output=parsed, stop_reason="end_turn", usage=usage)


def _grader(reasoning) -> tuple[Attest, _Messages]:
    client = AnthropicClient("claude-haiku-5-5", api_key="sk-ant-fake")
    messages = _Messages()
    client.client = types.SimpleNamespace(messages=messages)
    return Attest(client=client, reasoning=reasoning), messages


def test_the_default_is_auto_and_each_report_records_it():
    grader, messages = _grader("auto")
    report = grader.evaluate(RUN, checks=("faithfulness", "role"), verify=None)
    assert report.metadata["reasoning"] == {
        "faithfulness.extract": "auto",
        "faithfulness.verify": "auto",
        "role": "auto",
    }
    assert set(messages.efforts.values()) == {"low"}


def test_a_per_check_level_reaches_only_that_check():
    grader, messages = _grader({"role": "high", "default": "off"})
    report = grader.evaluate(RUN, checks=("faithfulness", "role"))
    assert report.metadata["reasoning"]["role"] == "high"
    assert report.metadata["reasoning"]["faithfulness.extract"] == "off"
    assert messages.efforts["_RoleOut"] == "high"
    assert messages.efforts["ClaimsOut"] == "low"


def test_a_report_with_no_model_call_records_no_levels():
    report = Attest(client=object()).evaluate(RUN, checks=("tool_use",))
    assert "reasoning" not in report.metadata


def test_attest_keeps_the_policy():
    assert Attest(reasoning="medium").reasoning == ReasoningPolicy(default="medium")


@pytest.mark.parametrize("bad", ["extreme", {"faithfulnes": "low"}])
def test_a_bad_setting_is_a_value_error(bad):
    with pytest.raises(ValueError):
        Attest(reasoning=bad)


@pytest.mark.parametrize("command", COMMANDS)
def test_every_model_command_rejects_a_bad_level(command, tmp_path):
    path = tmp_path / "in.json"
    path.write_text(json.dumps({"pr": {"diffs": {"a.py": "+x"}}}) if command == "review" else "{}")
    result = runner.invoke(app, [command, str(path), "--reasoning", "extreme"])
    assert result.exit_code == 2, result.output
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_input"
    assert "--reasoning" in payload["error"]["message"]


@pytest.mark.parametrize("command", ["role", "tools", "injection", "demo"])
def test_single_check_commands_pass_the_policy_to_the_model_context(command, monkeypatch, tmp_path):
    seen = {}
    module = sys.modules[f"attest.cli.commands.{command}"]

    def fake_context(provider, model, **kwargs):
        seen.update(kwargs)
        raise SystemExit(0)

    monkeypatch.setattr("attest.cli.context.resolve_key", lambda provider: "sk-test")
    monkeypatch.setattr(module, "llm_context", fake_context)
    path = tmp_path / "in.json"
    path.write_text(RUN.model_dump_json())
    extra = {"tools": ["--appropriate"], "injection": ["--deep"]}.get(command, [])
    runner.invoke(app, [command, str(path), *extra, "--reasoning", "role=high,default=low"])
    assert seen["reasoning"] == ReasoningPolicy(default="low", checks={"role": "high"})


def test_run_passes_the_policy_to_attest(monkeypatch, tmp_path):
    seen = {}
    module = sys.modules["attest.cli.commands.run"]

    class _Judge:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            raise SystemExit(0)

    monkeypatch.setattr("attest.cli.context.resolve_key", lambda provider: "sk-test")
    monkeypatch.setattr(module, "Attest", _Judge)
    path = tmp_path / "in.json"
    path.write_text(RUN.model_dump_json())
    runner.invoke(app, ["run", str(path), "--reasoning", "medium"])
    assert seen["reasoning"] == ReasoningPolicy(default="medium")
