"""Tool-use correctness — deterministic checks offline, `appropriate` mocks `call`."""

import attest.checks.tool_recovery as tr
import attest.checks.tool_use as tu
from attest.checks.tool_use import check_tool_use
from attest.trajectory import Step, ToolCall, Trajectory


def _traj(*calls, allowed=None, system_prompt=None, task="do a thing"):
    steps = [Step(tool_call=ToolCall(name=n, arguments=a, output=o)) for n, a, o in calls]
    return Trajectory(
        task=task,
        system_prompt=system_prompt,
        allowed_tools=allowed,
        steps=steps,
        final_answer="done",
    )


def test_all_allowed_no_errors_is_correct():
    result = check_tool_use(
        _traj(
            ("search", {"q": "x"}, "result A"),
            ("summarize", {}, "result B"),
            allowed=["search", "summarize"],
        )
    )
    assert result.check == "tool_use"
    assert result.score == 1.0
    assert result.passed
    assert all(f.verdict == "correct" for f in result.findings)
    assert "Sequence: search -> summarize" in result.summary


def test_disallowed_tool_fails():
    result = check_tool_use(
        _traj(
            ("search", {}, "ok"),
            ("delete_everything", {}, "done"),
            allowed=["search", "summarize"],
        )
    )
    bad = next(f for f in result.findings if f.subject == "delete_everything")
    assert bad.verdict == "disallowed_tool"
    assert bad.metadata["allowed"] is False
    assert "not in the agent's allowed tools" in bad.reason
    assert not result.passed


def test_error_followed_by_an_unrelated_call_is_not_handled():
    result = check_tool_use(
        _traj(
            ("fetch", {}, "Error: connection refused"),
            ("search", {}, "ok"),
            allowed=["search", "fetch"],
        )
    )
    err = result.findings[0]
    assert err.verdict == "error_silent"
    assert err.metadata["recovery"] == "unchecked"
    assert err.metadata["recovered_at"] is None
    assert err.evidence == "Error: connection refused"
    assert not result.passed


def test_retried_error_is_correct():
    result = check_tool_use(
        _traj(
            ("fetch", {}, "Error: timeout"),
            ("fetch", {}, "ok this time"),
            allowed=["fetch"],
        )
    )
    first = result.findings[0]
    assert first.metadata["recovery"] == "retried"
    assert first.metadata["recovered_at"] == 1
    assert first.verdict == "correct"
    assert result.passed


def test_disallowed_tool_takes_precedence_over_its_error():
    result = check_tool_use(_traj(("rm", {}, "Error: denied"), allowed=["search"]))
    finding = result.findings[0]
    assert finding.verdict == "disallowed_tool"
    assert finding.metadata["recovery"] == "unchecked"


def test_no_allowed_list_means_cannot_disallow():
    result = check_tool_use(_traj(("anything", {}, "ok")))
    assert result.findings[0].metadata["allowed"] is True
    assert result.findings[0].verdict == "correct"


def test_no_tool_calls():
    result = check_tool_use(Trajectory(task="t", final_answer="answered from memory"))
    assert result.findings == []
    assert result.score == 1.0
    assert result.summary == "No tool calls were made."


def test_appropriate_check_can_fail(monkeypatch):
    monkeypatch.setattr(
        tu,
        "call",
        lambda **k: tu._AppropriatenessOut(appropriate=False, reason="wrong tool for this"),
    )
    result = check_tool_use(
        _traj(("search", {}, "ok"), allowed=["search"], system_prompt="tools: search"),
        appropriate=True,
    )
    f = result.findings[0]
    assert f.metadata["appropriate"] is False
    assert f.verdict == "incorrect"
    assert "wrong tool" in f.reason


def test_appropriate_also_asks_about_unrecovered_errors(monkeypatch):
    monkeypatch.setattr(tu, "call", lambda **k: tu._AppropriatenessOut(appropriate=True))
    monkeypatch.setattr(tr, "call", lambda **k: tr._AnswerReport(outcome="succeeded"))
    result = check_tool_use(_traj(("pay", {}, "Error: declined")), appropriate=True)
    assert result.findings[0].verdict == "error_claimed_success"


def test_fast_mode_skips_llm(monkeypatch):
    def boom(**k):
        raise AssertionError("fast mode must not call the LLM")

    monkeypatch.setattr(tu, "call", boom)
    result = check_tool_use(_traj(("search", {}, "ok"), allowed=["search"]))
    assert result.findings[0].metadata["appropriate"] is None
