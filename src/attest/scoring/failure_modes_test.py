"""Every model-calling path, through the real `call`/`vote`, when the provider fails.

The fake client fails every call. `BudgetExceeded` must propagate; any other failure must be
inconclusive (`unverifiable` with `checked` false, or `unchecked`) and never a `pass`.
"""

import pytest
from pydantic import BaseModel, ValidationError

from attest import Attest, EvaluationPolicy, EvaluationRule
from attest.code_review import PullRequest, ReviewOutput
from attest.code_review.guidelines import parse_guidelines
from attest.llm import BudgetExceeded, ProviderConfigError
from attest.trajectory import Step, ToolCall, Trajectory


class ProviderError(Exception):
    status_code = 503


class _Strict(BaseModel):
    value: int


def _validation_error() -> ValidationError:
    try:
        _Strict.model_validate({})
    except ValidationError as error:
        return error
    raise AssertionError("expected a validation error")


PR = PullRequest(diffs={"a.py": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"})
OUTPUTS = [ReviewOutput(output_type="issue", text="x changes from 1 to 2.")]

FAILURES = {
    "provider_error": ProviderError("service unavailable"),
    "timeout": TimeoutError("the request timed out"),
    "malformed": _validation_error(),
    "none_response": None,
}


class FailingClient:
    """Fails every call: raises `failure`, or returns None when it is None."""

    def __init__(self, failure: BaseException | None) -> None:
        self.failure = failure
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return None


@pytest.fixture(params=sorted(FAILURES))
def failure(request) -> BaseException | None:
    return FAILURES[request.param]


@pytest.fixture
def grader(failure) -> Attest:
    return Attest(client=FailingClient(failure))


def _budget_grader(**kwargs) -> Attest:
    return Attest(client=FailingClient(BudgetExceeded("over budget")), **kwargs)


def _run(**overrides) -> Trajectory:
    fields = {
        "task": "What is the capital of France?",
        "system_prompt": "You answer geography questions only.",
        "steps": [Step(tool_call=ToolCall(name="search", output="Paris is the capital."))],
        "final_answer": "The capital of France is Paris.",
    }
    return Trajectory(**{**fields, **overrides})


def _errored_run() -> Trajectory:
    return _run(steps=[Step(tool_call=ToolCall(name="search", output="Error: timeout"))])


def _policy() -> EvaluationPolicy:
    rule = EvaluationRule(id="tone", description="The answer is polite.")
    return EvaluationPolicy(name="support", rules=(rule,))


def test_failed_claim_extraction_is_inconclusive(grader):
    report = grader.evaluate(_run(), checks=("faithfulness",))
    result = report.by("faithfulness")
    assert [f.verdict for f in result.findings] == ["unverifiable"]
    assert result.findings[0].metadata["checked"] is False
    assert "Claim extraction failed" in result.findings[0].reason
    assert result.score is None
    assert report.verdict == "review"


def test_failed_claim_verification_is_inconclusive(grader):
    report = grader.evaluate(_run(), checks=("faithfulness",), extract=lambda _: ["a", "b"])
    result = report.by("faithfulness")
    assert [f.metadata["checked"] for f in result.findings] == [False, False]
    assert result.metadata["claims_unchecked"] == 2
    assert report.verdict == "review"


def test_failed_role_judge_is_unchecked(grader):
    result = grader.role_adherence(_run())
    assert [f.verdict for f in result.findings] == ["unchecked"]
    assert "The role judge failed" in result.findings[0].reason
    assert grader.evaluate(_run(), checks=("role",)).verdict == "review"


def test_failed_deep_injection_is_unchecked(grader):
    result = grader.injection(_run(), deep=True)
    assert [f.verdict for f in result.findings] == ["unchecked"]
    assert "deep check failed" in result.summary
    assert grader.evaluate(_run(), checks=("injection",)).verdict == "review"


def test_failed_tool_choice_check_is_unchecked(grader):
    result = grader.tool_use(_run(), appropriate=True, check_answer=False)
    finding = result.findings[0]
    assert finding.verdict == "unchecked"
    assert "tool-choice check failed" in finding.reason
    assert result.score == 0.0
    report = grader.evaluate(_run(), checks=("tool_use",), appropriate=True)
    assert report.verdict == "review"


def test_failed_tool_error_answer_question_is_unchecked(grader):
    result = grader.tool_use(_errored_run(), check_answer=True)
    finding = result.findings[0]
    assert finding.verdict == "error_silent"
    assert finding.metadata["recovery"] == "unchecked"
    assert grader.evaluate(_errored_run(), checks=("tool_use",)).verdict == "review"


@pytest.mark.parametrize("kind", ["rubric", "evidence"])
def test_failed_policy_judge_is_unchecked(failure, kind):
    rule = EvaluationRule(id="r", description="The answer is backed by the tools.", kind=kind)
    grader = Attest(client=FailingClient(failure), policy=EvaluationPolicy(name="p", rules=(rule,)))
    result = grader.policy_check(_run())
    assert [f.verdict for f in result.findings] == ["unchecked"]
    assert "The policy judge failed" in result.findings[0].reason
    assert grader.evaluate(_run(), checks=("tool_use",)).verdict == "review"


def test_failed_review_grading_drops_every_output(grader):
    result = grader.review(PR, OUTPUTS)
    assert result.kept == []
    assert result.decisions[0].reasons[0].metadata["checked"] is False


def test_failed_guideline_check_raises_a_clear_error(grader):
    rules = parse_guidelines("- Name the changed line.\n", "REVIEW.md")
    with pytest.raises((ProviderError, TimeoutError, RuntimeError)):
        grader.review(PR, OUTPUTS, guidelines=rules)


MODEL_PATHS = pytest.mark.parametrize(
    "run_check",
    [
        lambda g: g.evaluate(_run(), checks=("faithfulness",)),
        lambda g: g.evaluate(_run(), checks=("faithfulness",), extract=lambda _: ["a"]),
        lambda g: g.role_adherence(_run()),
        lambda g: g.injection(_run(), deep=True),
        lambda g: g.tool_use(_run(), appropriate=True),
        lambda g: g.tool_use(_errored_run(), check_answer=True),
    ],
    ids=["extract", "verify", "role", "deep_injection", "tool_choice", "tool_error_answer"],
)


@MODEL_PATHS
def test_budget_exceeded_always_propagates(run_check):
    with pytest.raises(BudgetExceeded):
        run_check(_budget_grader())


def test_budget_exceeded_propagates_from_policy_rules():
    with pytest.raises(BudgetExceeded):
        _budget_grader(policy=_policy()).policy_check(_run())


def test_budget_exceeded_propagates_from_review():
    with pytest.raises(BudgetExceeded):
        _budget_grader().review(PR, OUTPUTS)


def test_malformed_responses_are_retried_before_failing():
    client = FailingClient(None)
    Attest(client=client).role_adherence(_run())
    assert client.calls == 3


class _AuthError(Exception):
    status_code = 401


def _bad_key_grader(**kwargs) -> Attest:
    return Attest(client=FailingClient(_AuthError("invalid x-api-key")), **kwargs)


@MODEL_PATHS
def test_a_bad_api_key_stops_every_check(run_check):
    with pytest.raises(ProviderConfigError) as raised:
        run_check(_bad_key_grader())
    assert raised.value.problem == "authentication"


def test_a_bad_api_key_stops_policy_rules():
    with pytest.raises(ProviderConfigError):
        _bad_key_grader(policy=_policy()).policy_check(_run())


def test_a_bad_api_key_stops_review():
    with pytest.raises(ProviderConfigError):
        _bad_key_grader().review(PR, OUTPUTS)
