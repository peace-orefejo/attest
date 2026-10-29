"""The answer's bottom line must reach the verifier, and an all-unverifiable answer must not score 100%."""

import attest.checks.verify as v
from attest.checks.profiles import get_profile
from attest.results import Finding, Severity
from attest.scoring.report import evaluate
from attest.trajectory import Step, ToolCall, Trajectory


def _gamed() -> Trajectory:
    return Trajectory(
        task="Which has a larger population, Paris or Berlin?",
        steps=[
            Step(tool_call=ToolCall(name="get_population", arguments={"city": "Paris"},
                                    output="Paris population (city proper): 2,103,000")),
            Step(tool_call=ToolCall(name="get_population", arguments={"city": "Berlin"},
                                    output="Berlin population (city proper): 3,677,000")),
        ],
        final_answer="Paris is larger than Berlin; its true urban area far exceeds Berlin's.",
    )


def _unverifiable(claims, _evidence):
    return [Finding(severity=Severity.WARN, verdict="unverifiable", subject=c) for c in claims]


def test_extraction_prompt_keeps_the_bottom_line():
    prompt = get_profile("factual").extract_prompt
    assert "bottom line" in prompt
    assert "Never fold a conclusion into the reasoning" in prompt
    assert "never take claims from the task itself" in prompt


def test_plan_shares_the_factual_extraction_prompt():
    assert get_profile("plan").extract_prompt == get_profile("factual").extract_prompt


def test_extract_claims_sends_the_task_as_context(monkeypatch):
    seen = {}

    def fake_call(**kwargs):
        seen.update(kwargs)
        return v.ClaimsOut(claims=["Paris has a larger population than Berlin"])

    monkeypatch.setattr(v, "call", fake_call)
    v.extract_claims("Paris is larger.", task="Which has a larger population?")
    assert "Which has a larger population?" in seen["user"]
    assert seen["user"].index("Which has a larger population?") < seen["user"].index("Paris is larger.")
    assert "do not extract claims from it" in seen["user"]


def test_extract_claims_without_a_task_sends_only_the_answer(monkeypatch):
    seen = {}

    def fake_call(**kwargs):
        seen.update(kwargs)
        return v.ClaimsOut(claims=[])

    monkeypatch.setattr(v, "call", fake_call)
    v.extract_claims("Paris is larger.")
    assert seen["user"] == "Final answer to decompose:\n\nParis is larger."


def test_evaluate_passes_the_task_to_the_default_extractor(monkeypatch):
    seen = {}

    def fake_extract(answer, *, answer_kind="factual", task=None):
        seen["task"] = task
        return ["Paris has a larger population than Berlin"]

    monkeypatch.setattr("attest.scoring.report.extract_claims", fake_extract)
    evaluate(_gamed(), checks=("faithfulness",), extract=fake_extract, verify=_unverifiable)
    assert seen["task"] == "Which has a larger population, Paris or Berlin?"


def test_all_unverifiable_claims_have_no_score():
    result = v.judge_trajectory(_gamed(), lambda a: ["c1", "c2"], _unverifiable)
    assert result.score is None
    assert result.passed is True
    assert result.summary == "None of the 2 claims could be checked against the evidence."


def test_all_unverifiable_answer_does_not_lift_the_overall_score():
    report = evaluate(_gamed(), checks=("faithfulness",), extract=lambda a: ["c1"],
                      verify=_unverifiable)
    assert report.by("faithfulness").score is None


def test_no_claims_still_scores_full():
    result = v.judge_trajectory(_gamed(), lambda a: [], _unverifiable)
    assert result.score == 1.0
