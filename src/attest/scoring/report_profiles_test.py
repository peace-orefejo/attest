"""evaluate() resolves the answer kind and sends its prompts to both stages — `call` mocked."""

import pytest

import attest.checks.verify as v
from attest import Attest
from attest.checks.profiles import get_profile
from attest.prompts.faithfulness import BATCH_INSTRUCTION
from attest.prompts.profiles import factual
from attest.results import Finding, Severity
from attest.scoring.report import evaluate
from attest.trajectory import Step, ToolCall, Trajectory

DIFF = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-timeout = 600\n+timeout = 900\n"


def _code_traj() -> Trajectory:
    return Trajectory(
        task="Review the diff and report bugs.",
        steps=[
            Step(tool_call=ToolCall(name="read_diff", arguments={"path": "app.py"}, output=DIFF))
        ],
        final_answer="The timeout is now 15 minutes.",
    )


def _factual_traj() -> Trajectory:
    return Trajectory(
        task="How big is Paris?",
        steps=[
            Step(
                tool_call=ToolCall(
                    name="search",
                    arguments={"query": "Paris"},
                    output="Paris has 2,103,000 residents.",
                )
            )
        ],
        final_answer="Paris has about 2.1 million residents.",
    )


def _gamed() -> Trajectory:
    return Trajectory(
        task="Which has a larger population, Paris or Berlin?",
        steps=[
            Step(
                tool_call=ToolCall(
                    name="get_population",
                    arguments={"city": "Paris"},
                    output="Paris population (city proper): 2,103,000",
                )
            ),
            Step(
                tool_call=ToolCall(
                    name="get_population",
                    arguments={"city": "Berlin"},
                    output="Berlin population (city proper): 3,677,000",
                )
            ),
        ],
        final_answer="Paris is larger than Berlin; its true urban area far exceeds Berlin's.",
    )


def _unverifiable(claims, _evidence):
    return [Finding(severity=Severity.WARN, verdict="unverifiable", subject=c) for c in claims]


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
    return BATCH_INSTRUCTION + get_profile(kind).verify_prompt


def test_evaluate_code_sends_code_prompts_to_both_stages(seen):
    report = evaluate(_code_traj(), checks=["faithfulness"], answer_kind="code")
    assert seen["extract"] == [get_profile("code").extract_prompt]
    assert seen["verify"] == [_batch("code")]
    assert report.metadata == {}


def test_evaluate_factual_prompts_unchanged(seen):
    report = evaluate(_factual_traj(), checks=["faithfulness"])
    assert seen["extract"] == [factual.EXTRACT_PROMPT]
    assert seen["verify"] == [_batch("factual")]
    assert report.metadata == {}


def test_evaluate_plan_uses_factual_extraction_and_plan_standard(seen):
    evaluate(_factual_traj(), checks=["faithfulness"], answer_kind="plan")
    assert seen["extract"] == [factual.EXTRACT_PROMPT]
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
    assert seen["extract"] == [factual.EXTRACT_PROMPT]
    assert seen["verify"] == [_batch("factual")]


def test_evaluate_auto_records_metadata_without_faithfulness(seen):
    report = evaluate(_code_traj(), checks=["tool_use"], answer_kind="auto")
    assert report.metadata["answer_kind"] == "code"
    assert seen == {"extract": [], "verify": []}


def test_explicit_factual_on_code_evidence_hints_without_changing_grading(seen):
    report = evaluate(_code_traj(), checks=["faithfulness"], answer_kind="factual")
    assert report.metadata == {"answer_kind_hint": "code"}
    assert seen["extract"] == [factual.EXTRACT_PROMPT]
    assert seen["verify"] == [_batch("factual")]


def test_explicit_code_and_plan_get_no_hint(seen):
    report = evaluate(_code_traj(), checks=["tool_use"], answer_kind="plan")
    assert "answer_kind_hint" not in report.metadata


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
        _code_traj(), checks=["faithfulness"], answer_kind="auto"
    )
    assert report.metadata["answer_kind"] == "code"
    assert seen["extract"] == [get_profile("code").extract_prompt]


def test_evaluate_passes_the_task_to_the_default_extractor(monkeypatch):
    seen = {}

    def fake_extract(answer, *, answer_kind="factual", task=None):
        seen["task"] = task
        return ["Paris has a larger population than Berlin"]

    monkeypatch.setattr("attest.scoring.report.extract_claims", fake_extract)
    evaluate(_gamed(), checks=("faithfulness",), extract=fake_extract, verify=_unverifiable)
    assert seen["task"] == "Which has a larger population, Paris or Berlin?"


def test_all_unverifiable_answer_does_not_lift_the_overall_score():
    report = evaluate(
        _gamed(), checks=("faithfulness",), extract=lambda a: ["c1"], verify=_unverifiable
    )
    assert report.by("faithfulness").score is None
    assert report.overall_score is None
