"""--exclude, --exclude-file and .attestignore discovery on `attest run` and `attest review`."""

import json

import pytest
from typer.testing import CliRunner

from attest import Attest, CheckResult, Report
from attest.cli import app
from attest.code_review import ReviewResult

runner = CliRunner(env={"COLUMNS": "200", "TERMINAL_WIDTH": "200"})


@pytest.fixture
def seen(monkeypatch):
    captured: dict = {}

    def fake_review(self, pr, outputs, **kwargs):
        captured["exclusions"] = self.exclusions
        injection = CheckResult(check="code_injection", passed=True, metadata={"verdict": "clean"})
        return ReviewResult(decisions=[], injection=injection)

    def fake_evaluate(self, traj, **kwargs):
        captured["exclusions"] = self.exclusions
        return Report(results=[CheckResult(check="tool_use", passed=True, score=1.0)])

    monkeypatch.setattr(Attest, "review", fake_review)
    monkeypatch.setattr(Attest, "evaluate", fake_evaluate)
    monkeypatch.setattr("attest.cli.context.resolve_key", lambda provider: "sk-test")
    return captured


def _inputs(tmp_path) -> dict[str, str]:
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"pr": {"diffs": {"a.py": "+x = 1\n"}}, "outputs": []}))
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"task": "t", "final_answer": "a"}))
    return {"review": str(review), "run": str(run)}


def _error(result) -> str:
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"
    return payload["error"]["message"]


@pytest.mark.parametrize("command", ["review", "run"])
def test_attestignore_is_discovered_then_cli_patterns_apply(tmp_path, monkeypatch, seen, command):
    (tmp_path / ".attestignore").write_text("# private\nsecrets/\n*.csv\n")
    monkeypatch.chdir(tmp_path)
    args = [command, _inputs(tmp_path)[command], "--exclude", "!keep.csv", "--exclude", "*.pem"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    exclusions = seen["exclusions"]
    assert exclusions.patterns == ("# private", "secrets/", "*.csv", "!keep.csv", "*.pem")
    assert exclusions.excludes("secrets/a.env") and exclusions.excludes("big.csv")
    assert not exclusions.excludes("keep.csv")


@pytest.mark.parametrize("command", ["review", "run"])
def test_no_attestignore_turns_discovery_off(tmp_path, monkeypatch, seen, command):
    (tmp_path / ".attestignore").write_text("secrets/\n")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, [command, _inputs(tmp_path)[command], "--no-attestignore"])
    assert result.exit_code == 0, result.output
    assert not seen["exclusions"].active


def test_exclude_file_is_read_after_attestignore(tmp_path, monkeypatch, seen):
    (tmp_path / ".attestignore").write_text("data/\n")
    extra = tmp_path / "team.ignore"
    extra.write_text("*.parquet\n")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["review", _inputs(tmp_path)["review"], "--exclude-file", str(extra)]
    )
    assert result.exit_code == 0, result.output
    assert seen["exclusions"].patterns == ("data/", "*.parquet")
    assert seen["exclusions"].sources == (str(tmp_path / ".attestignore"), str(extra))


def test_without_any_source_nothing_is_excluded(tmp_path, monkeypatch, seen):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", _inputs(tmp_path)["run"]])
    assert result.exit_code == 0, result.output
    assert not seen["exclusions"].active


@pytest.mark.parametrize("command", ["review", "run"])
def test_an_unreadable_exclude_file_is_invalid_input(tmp_path, monkeypatch, seen, command):
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing.ignore"
    result = runner.invoke(
        app, [command, _inputs(tmp_path)[command], "--exclude-file", str(missing)]
    )
    assert result.exit_code == 2
    assert "Could not read exclusion file" in _error(result)
    assert "exclusions" not in seen


def test_an_unreadable_attestignore_is_invalid_input(tmp_path, monkeypatch, seen):
    (tmp_path / ".attestignore").mkdir()
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["review", _inputs(tmp_path)["review"]])
    assert result.exit_code == 2
    assert "Could not read exclusion file" in _error(result)


def test_an_oversized_pattern_file_is_invalid_input(tmp_path, monkeypatch, seen):
    big = tmp_path / "big.ignore"
    big.write_text("x" * 1_048_577)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", _inputs(tmp_path)["run"], "--exclude-file", str(big)])
    assert result.exit_code == 2
    assert "1 MB" in _error(result)


def test_too_many_patterns_is_invalid_input(tmp_path, monkeypatch, seen):
    many = tmp_path / "many.ignore"
    many.write_text("\n".join(f"f{i}" for i in range(1_000)))
    monkeypatch.chdir(tmp_path)
    args = ["review", _inputs(tmp_path)["review"], "--exclude-file", str(many), "--exclude", "x"]
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "Too many exclusion patterns" in _error(result)


def _review_changing(tmp_path, *paths: str) -> str:
    review = tmp_path / "review.json"
    diffs = {path: f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n+src/evil.py\n" for path in paths}
    review.write_text(json.dumps({"pr": {"diffs": {"src/evil.py": "+x\n", **diffs}}}))
    return str(review)


def test_a_pull_request_editing_the_discovered_attestignore_is_refused(tmp_path, monkeypatch, seen):
    (tmp_path / ".attestignore").write_text("src/evil.py\n")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["review", _review_changing(tmp_path, ".attestignore")])
    assert result.exit_code == 2
    message = _error(result)
    assert "could hide its own changes" in message
    assert "--allow-pr-attestignore" in message and "base branch" in message
    assert "exclusions" not in seen


def test_a_pull_request_editing_an_exclude_file_in_the_repo_is_refused(tmp_path, monkeypatch, seen):
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / "team.ignore").write_text("src/evil.py\n")
    sub = tmp_path / "packages" / "app"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    args = ["review", _review_changing(tmp_path, "ci/team.ignore"), "--exclude-file"]
    result = runner.invoke(app, [*args, str(tmp_path / "ci" / "team.ignore")])
    assert result.exit_code == 2
    assert "ci/team.ignore" in _error(result)


def test_the_override_flag_or_untouched_files_let_the_review_run(tmp_path, monkeypatch, seen):
    (tmp_path / ".attestignore").write_text("src/evil.py\n")
    monkeypatch.chdir(tmp_path)
    allowed = ["review", _review_changing(tmp_path, ".attestignore"), "--allow-pr-attestignore"]
    assert runner.invoke(app, allowed).exit_code == 0
    assert seen["exclusions"].excludes("src/evil.py")
    other = ["review", _review_changing(tmp_path, "docs/.attestignore")]
    assert runner.invoke(app, other).exit_code == 0
    no_discovery = ["review", _review_changing(tmp_path, ".attestignore"), "--no-attestignore"]
    assert runner.invoke(app, no_discovery).exit_code == 0
