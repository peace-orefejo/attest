"""Answer-kind profiles reach the model through extraction and verification — `call` mocked."""

import pytest

import attest.checks.verify as v
from attest.checks.profiles import get_profile
from attest.prompts.faithfulness import BATCH_INSTRUCTION
from attest.prompts.profiles import factual, plan


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


def test_extract_claims_defaults_to_factual_prompt(seen):
    v.extract_claims("an answer")
    assert seen["extract"] == [factual.EXTRACT_PROMPT]


def test_extract_claims_plan_uses_factual_prompt(seen):
    v.extract_claims("an answer", answer_kind="plan")
    assert seen["extract"] == [factual.EXTRACT_PROMPT]


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
    assert seen["verify"] == [
        BATCH_INSTRUCTION + factual.VERIFY_PROMPT,
        BATCH_INSTRUCTION + plan.VERIFY_PROMPT,
    ]


def test_grounded_verifier_code_uses_code_standard(seen):
    v.grounded_verifier("claim", "evidence", answer_kind="code")
    assert seen["verify"] == [get_profile("code").verify_prompt]


@pytest.mark.parametrize(
    "fn",
    [
        lambda: v.extract_claims("answer", answer_kind="creative"),
        lambda: v.extract_claims("", answer_kind="creative"),
        lambda: v.verify_claims(["c"], "evidence", answer_kind="creative"),
        lambda: v.verify_claims([], "evidence", answer_kind="creative"),
        lambda: v.grounded_verifier("c", "evidence", answer_kind="creative"),
        lambda: v.verify_claims(["c"], "evidence", answer_kind="auto"),
    ],
)
def test_unknown_kind_raises_instead_of_falling_back(seen, fn):
    with pytest.raises(ValueError):
        fn()
    assert seen == {"extract": [], "verify": []}
