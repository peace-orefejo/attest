"""Answer-kind profiles reach the model through extraction and verification — `call` mocked."""

import pytest

import attest.checks.verify as v
from attest import Attest
from attest.checks.profiles import get_profile
from attest.scoring.report import evaluate
from attest.trajectory import Step, ToolCall, Trajectory

DIFF = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-timeout = 600\n+timeout = 900\n"


def _code_traj() -> Trajectory:
    return Trajectory(
        task="Review the diff and report bugs.",
        steps=[Step(tool_call=ToolCall(name="read_diff", arguments={"path": "app.py"},
                                       output=DIFF))],
        final_answer="The timeout is now 15 minutes.",
    )


def _factual_traj() -> Trajectory:
    return Trajectory(
        task="How big is Paris?",
        steps=[Step(tool_call=ToolCall(name="search", arguments={"query": "Paris"},
                                       output="Paris has 2,103,000 residents."))],
        final_answer="Paris has about 2.1 million residents.",
    )


@pytest.fixture
def seen(monkeypatch):
    calls: dict[str, list[str]] = {"extract": [], "verify": []}

    def fake_call(*, system, user, output, **_):
        if output is v.ClaimsOut:
            calls["extract"].append(system)
            return v.ClaimsOut(claims=["claim one"])
        if output is v.VerdictOut:
            calls["verify"].append(system)
            return v.VerdictOut(verdict="supported")
        calls["verify"].append(system)
        return v._BatchOut(verdicts=[v._ClaimVerdict(claim=1, verdict="supported")])

    monkeypatch.setattr(v, "call", fake_call)
    return calls


def _batch(kind: str) -> str:
    return v._BATCH_INSTRUCTION + get_profile(kind).verify_prompt


def test_extract_claims_defaults_to_factual_prompt(seen):
    v.extract_claims("an answer")
    assert seen["extract"] == [v._EXTRACT_SYSTEM]


def test_extract_claims_plan_uses_factual_prompt(seen):
    v.extract_claims("an answer", answer_kind="plan")
    assert seen["extract"] == [v._EXTRACT_SYSTEM]


def test_extract_claims_code_uses_code_prompt(seen):
    v.extract_claims("an answer", answer_kind="code")
    assert seen["extract"] == [get_profile("code").extract_prompt]


@pytest.mark.parametrize("kind", ["factual", "plan", "code"])
def test_verify_claims_uses_kind_standard(seen, kind):
    v.verify_claims(["claim"], "evidence", answer_kind=kind)
    assert seen["verify"] == [_batch(kind)]


def test_verify_claims_factual_and_plan_unchanged(seen):
    v.verify_claims(["claim"], "evidence")
    v.verify_claims(["claim"], "evidence", answer_kind="plan")
    assert seen["verify"] == [v._BATCH_INSTRUCTION + v._VERIFY_SYSTEM["factual"],
                              v._BATCH_INSTRUCTION + v._VERIFY_SYSTEM["plan"]]


def test_grounded_verifier_code_uses_code_standard(seen):
    v.grounded_verifier("claim", "evidence", answer_kind="code")
    assert seen["verify"] == [get_profile("code").verify_prompt]


@pytest.mark.parametrize("fn", [
    lambda: v.extract_claims("answer", answer_kind="creative"),
    lambda: v.extract_claims("", answer_kind="creative"),
    lambda: v.verify_claims(["c"], "evidence", answer_kind="creative"),
    lambda: v.grounded_verifier("c", "evidence", answer_kind="creative"),
    lambda: v.verify_claims(["c"], "evidence", answer_kind="auto"),
])
def test_unknown_kind_raises_instead_of_falling_back(seen, fn):
    with pytest.raises(ValueError):
        fn()
    assert seen == {"extract": [], "verify": []}


def test_evaluate_code_sends_code_prompts_to_both_stages(seen):
    report = evaluate(_code_traj(), checks=["faithfulness"], answer_kind="code")
    assert seen["extract"] == [get_profile("code").extract_prompt]
    assert seen["verify"] == [_batch("code")]
    assert report.metadata == {}


def test_evaluate_factual_prompts_unchanged(seen):
    report = evaluate(_factual_traj(), checks=["faithfulness"])
    assert seen["extract"] == [v._EXTRACT_SYSTEM]
    assert seen["verify"] == [_batch("factual")]
    assert report.metadata == {}


def test_evaluate_plan_uses_factual_extraction_and_plan_standard(seen):
    evaluate(_factual_traj(), checks=["faithfulness"], answer_kind="plan")
    assert seen["extract"] == [v._EXTRACT_SYSTEM]
    assert seen["verify"] == [_batch("plan")]


def test_evaluate_auto_resolves_code_and_records_metadata(seen):
    report = evaluate(_code_traj(), checks=["faithfulness"], answer_kind="auto")
    assert report.metadata["answer_kind"] == "code"
    assert "read_diff" in report.metadata["answer_kind_reason"]
    assert seen["extract"] == [get_profile("code").extract_prompt]
    assert seen["verify"] == [_batch("code")]


def test_evaluate_auto_resolves_factual_and_records_metadata(seen):
    report = evaluate(_factual_traj(), checks=["faithfulness"], answer_kind="auto")
    assert report.metadata["answer_kind"] == "factual"
    assert report.metadata["answer_kind_reason"]
    assert seen["extract"] == [v._EXTRACT_SYSTEM]
    assert seen["verify"] == [_batch("factual")]


def test_evaluate_auto_records_metadata_without_faithfulness(seen):
    report = evaluate(_code_traj(), checks=["tool_use"], answer_kind="auto")
    assert report.metadata["answer_kind"] == "code"
    assert seen == {"extract": [], "verify": []}


def test_explicit_factual_on_code_evidence_hints_without_changing_grading(seen):
    report = evaluate(_code_traj(), checks=["faithfulness"], answer_kind="factual")
    assert report.metadata == {"answer_kind_hint": "code"}
    assert seen["extract"] == [v._EXTRACT_SYSTEM]
    assert seen["verify"] == [_batch("factual")]


def test_explicit_code_and_plan_get_no_hint(seen):
    assert "answer_kind_hint" not in evaluate(
        _code_traj(), checks=["tool_use"], answer_kind="plan").metadata


def test_custom_extractor_is_not_rebound(seen):
    got = []

    def custom(answer):
        got.append(answer)
        return ["claim one"]

    evaluate(_code_traj(), checks=["faithfulness"], answer_kind="code", extract=custom)
    assert got == ["The timeout is now 15 minutes."]
    assert seen["extract"] == []
    assert seen["verify"] == [_batch("code")]


@pytest.mark.parametrize("kind", ["creative", "Code", ""])
def test_evaluate_unknown_kind_still_raises(seen, kind):
    with pytest.raises(ValueError, match="answer kind"):
        evaluate(_code_traj(), answer_kind=kind)
    assert seen == {"extract": [], "verify": []}


def test_attest_evaluate_auto_keeps_resolved_metadata(seen):
    report = Attest(client=object()).evaluate(
        _code_traj(), checks=["faithfulness"], answer_kind="auto")
    assert report.metadata["answer_kind"] == "code"
    assert seen["extract"] == [get_profile("code").extract_prompt]
