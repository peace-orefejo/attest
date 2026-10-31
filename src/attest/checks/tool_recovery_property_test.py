"""Property tests: recovery classification and the tool-use score, over generated runs."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given
from hypothesis import strategies as st

import attest.checks.tool_recovery as tr
import attest.checks.tool_use as tu
from attest.checks.tool_recovery import is_error
from attest.checks.tool_use import check_tool_use
from attest.results import CheckResult, Severity
from attest.trajectory import Step, ToolCall, Trajectory

TOOLS = ["search", "fetch", "backup", "delete"]
OUTPUTS = [
    "ok",
    "3 results",
    "",
    "   ",
    "Error: timeout",
    "exception raised",
    "Traceback (most recent call last):\n  boom",
    "the error: rate limited",
    "no errors found",
    "Exception: nope",
]
OUTCOMES = ["failed", "succeeded", "not_mentioned"]

tool_names = st.sampled_from(TOOLS)
tool_calls = st.builds(
    ToolCall,
    name=tool_names,
    output=st.sampled_from(OUTPUTS) | st.text(max_size=20),
    is_error=st.none() | st.booleans(),
)
runs = st.builds(
    Trajectory,
    task=st.just("do a thing"),
    allowed_tools=st.none() | st.lists(tool_names, unique=True),
    tool_fallbacks=st.dictionaries(tool_names, st.lists(tool_names, max_size=2), max_size=3),
    steps=st.lists(st.builds(Step, tool_call=st.none() | tool_calls), max_size=6),
    final_answer=st.just("done"),
)


@contextmanager
def _answer(outcome: str | None) -> Iterator[list[int]]:
    """Stub the answer question: answer `outcome`, raise if None, and count the calls."""
    asked: list[int] = []

    def fake(**kwargs):
        asked.append(1)
        if outcome is None:
            raise RuntimeError("no model in property tests")
        return tr._AnswerReport(outcome=outcome, reason="stubbed")

    def no_appropriateness(**kwargs):
        raise AssertionError("the appropriateness check must not run")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tr, "call", fake)
        patch.setattr(tu, "call", no_appropriateness)
        yield asked


def _calls_by_step(run: Trajectory) -> dict[int, ToolCall]:
    return {step: call for step, call in run.tool_calls()}


def _first_recovery(run: Trajectory, step: int, call: ToolCall) -> tuple[str, int] | None:
    fallbacks = run.tool_fallbacks.get(call.name, [])
    for later_step, later in run.tool_calls():
        if later_step > step and not is_error(later):
            if later.name == call.name:
                return "retried", later_step
            if later.name in fallbacks:
                return "fallback", later_step
    return None


@given(runs)
def test_without_the_answer_check_no_model_runs_and_errors_are_never_judged(run):
    with _answer(None) as asked:
        result = check_tool_use(run, check_answer=False)
    assert not asked
    calls = _calls_by_step(run)
    for finding in result.findings:
        recovery = finding.metadata["recovery"]
        if is_error(calls[finding.step]):
            assert recovery in ("retried", "fallback", "unchecked")
        else:
            assert recovery is None


@given(runs, st.sampled_from([*OUTCOMES, None]))
def test_retries_and_fallbacks_point_at_the_first_later_success(run, outcome):
    with _answer(outcome):
        result = check_tool_use(run, check_answer=True)
    calls = _calls_by_step(run)
    for finding in result.findings:
        call = calls[finding.step]
        recovery, at = finding.metadata["recovery"], finding.metadata["recovered_at"]
        if not is_error(call):
            continue
        expected = _first_recovery(run, finding.step, call)
        if expected is not None:
            assert (recovery, at) == expected
            continue
        assert at is None
        assert recovery in ("acknowledged", "silent", "claimed_success", "unchecked")


@given(runs, st.sampled_from([*OUTCOMES, None]))
def test_retried_and_fallback_targets_are_later_successful_calls(run, outcome):
    with _answer(outcome):
        result = check_tool_use(run, check_answer=True)
    calls = _calls_by_step(run)
    for finding in result.findings:
        at = finding.metadata["recovered_at"]
        if finding.metadata["recovery"] not in ("retried", "fallback"):
            assert at is None
            continue
        assert isinstance(at, int) and finding.step is not None
        assert at > finding.step and not is_error(calls[at])
        if finding.metadata["recovery"] == "retried":
            assert calls[at].name == finding.subject
        else:
            assert calls[at].name in run.tool_fallbacks[finding.subject]


@given(runs, st.sampled_from([*OUTCOMES, None]))
def test_disallowed_tools_always_win_and_error_free_allowed_calls_are_correct(run, outcome):
    with _answer(outcome):
        result = check_tool_use(run, check_answer=True)
    allowed = set(run.allowed_tools or [])
    calls = _calls_by_step(run)
    for finding in result.findings:
        call = calls[finding.step]
        if allowed and call.name not in allowed:
            assert finding.verdict == "disallowed_tool"
        elif not is_error(call):
            assert finding.verdict == "correct"


@given(runs, st.sampled_from(OUTCOMES))
def test_the_answer_decides_unrecovered_errors(run, outcome):
    with _answer(outcome):
        result = check_tool_use(run, check_answer=True)
    expected = {
        "failed": ("acknowledged", "correct"),
        "not_mentioned": ("silent", "error_silent"),
        "succeeded": ("claimed_success", "error_claimed_success"),
    }[outcome]
    allowed = set(run.allowed_tools or [])
    for finding in result.findings:
        recovery = finding.metadata["recovery"]
        if recovery in (None, "retried", "fallback"):
            continue
        assert recovery == expected[0]
        if not allowed or finding.subject in allowed:
            assert finding.verdict == expected[1]


def _assert_score_and_passed(result: CheckResult, run: Trajectory) -> None:
    assert [f.step for f in result.findings] == [step for step, _ in run.tool_calls()]
    correct = [f.verdict == "correct" for f in result.findings]
    assert result.score == (sum(correct) / len(correct) if correct else 1.0)
    assert result.passed == (not any(f.severity is Severity.FAIL for f in result.findings))
    assert result.passed == all(correct)


@given(runs, st.sampled_from([*OUTCOMES, None]), st.booleans())
def test_score_is_the_share_of_correct_findings(run, outcome, check_answer):
    with _answer(outcome):
        result = check_tool_use(run, check_answer=check_answer)
    _assert_score_and_passed(result, run)


@given(runs)
def test_a_run_without_errors_is_all_correct_when_its_tools_are_allowed(run):
    clean = run.model_copy(
        update={
            "allowed_tools": None,
            "steps": [
                Step(tool_call=c.model_copy(update={"is_error": False}))
                for _, c in run.tool_calls()
            ],
        }
    )
    with _answer(None) as asked:
        result = check_tool_use(clean, check_answer=True)
    assert not asked
    assert all(f.verdict == "correct" for f in result.findings)
    assert result.passed and result.score == 1.0
