"""`--max-claims` on `attest run` and `attest review`: passed through, negatives rejected."""

import json

import pytest
from typer.testing import CliRunner

from attest import Attest, CheckResult, Report
from attest.cli import app
from attest.code_review import ReviewResult

runner = CliRunner(env={"COLUMNS": "200", "TERMINAL_WIDTH": "200"})

TRAJECTORY = {
    "task": "search",
    "steps": [{"tool_call": {"name": "search", "arguments": {}, "output": "found"}}],
    "final_answer": "found",
}
REVIEW = {
    "pr": {"diffs": {"a.py": "+x = 1\n"}, "changed_files": ["a.py"]},
    "outputs": [{"output_type": "issue", "text": "x is set to 1."}],
}


@pytest.fixture
def seen(monkeypatch) -> dict:
    calls: dict = {}

    def fake_evaluate(self, traj, **kwargs):
        calls["run"] = kwargs
        return Report(results=[CheckResult(check="tool_use", passed=True, score=1.0)])

    def fake_review(self, pr, outputs, **kwargs):
        calls["review"] = kwargs
        return ReviewResult(
            decisions=[], injection=CheckResult(check="code_injection", passed=True)
        )

    monkeypatch.setattr(Attest, "evaluate", fake_evaluate)
    monkeypatch.setattr(Attest, "review", fake_review)
    monkeypatch.setattr("attest.cli.context.resolve_key", lambda provider: "sk-test")
    return calls


def _file(tmp_path, name: str, content: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(content))
    return str(path)


@pytest.mark.parametrize(("args", "expected"), [([], 40), (["--max-claims", "5"], 5)])
def test_run_passes_max_claims_to_evaluate(tmp_path, seen, args, expected):
    path = _file(tmp_path, "run.json", TRAJECTORY)
    result = runner.invoke(app, ["run", path, "--checks", "tool_use", *args])
    assert result.exit_code == 0, result.output
    assert seen["run"]["max_claims"] == expected


@pytest.mark.parametrize(("args", "expected"), [([], 40), (["--max-claims", "0"], 0)])
def test_review_passes_max_claims_to_review(tmp_path, seen, args, expected):
    result = runner.invoke(app, ["review", _file(tmp_path, "review.json", REVIEW), *args])
    assert result.exit_code == 0, result.output
    assert seen["review"]["max_claims"] == expected


@pytest.mark.parametrize(
    ("command", "name", "content"), [("run", "run.json", TRAJECTORY), ("review", "r.json", REVIEW)]
)
def test_a_negative_max_claims_is_invalid_input(tmp_path, seen, command, name, content):
    result = runner.invoke(app, [command, _file(tmp_path, name, content), "--max-claims", "-1"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"
    assert payload["error"]["message"] == "--max-claims: must be 0 or more, not -1."
    assert seen == {}
