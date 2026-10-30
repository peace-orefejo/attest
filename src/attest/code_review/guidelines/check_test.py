"""check_guidelines keeps only violations that name a real rule and quote the output exactly."""

import pytest

import attest.code_review.guidelines.check as g
from attest import Severity
from attest.code_review import ReviewOutput
from attest.code_review.guidelines import parse_guidelines
from attest.code_review.guidelines.confirm import ConfirmOut

RULES = parse_guidelines(
    "- Do not flag formatting.\n- Name the function an issue is about.\n", "REVIEW.md"
)
OUTPUT = ReviewOutput(
    output_type="issue", text="Line 4 has  inconsistent indentation; please reformat."
)


@pytest.fixture(autouse=True)
def confirmed(monkeypatch):
    asked = []

    def fake_confirm(rule, output, quote):
        asked.append((rule.id, quote))
        return ConfirmOut(does_itself=True, reason="Confirmed.")

    monkeypatch.setattr(g, "confirm_break", fake_confirm)
    return asked


def _answer(monkeypatch, *violations):
    seen = {}

    def fake_call(**kwargs):
        seen.update(kwargs)
        return g.ViolationsOut(violations=[g.Violation(**v) for v in violations])

    monkeypatch.setattr(g, "call", fake_call)
    return seen


def test_a_quoted_violation_becomes_a_failing_finding(monkeypatch):
    _answer(
        monkeypatch,
        {"rule": "G1", "quote": "has inconsistent indentation", "reason": "It flags formatting."},
    )
    result = g.check_guidelines(OUTPUT, RULES, evidence="+    x = 1")
    assert result.check == "guidelines"
    assert not result.passed
    finding = result.findings[0]
    assert finding.severity is Severity.FAIL
    assert finding.verdict == "breaks_guideline"
    assert finding.subject == "G1: Do not flag formatting."
    assert finding.evidence == "has inconsistent indentation"
    assert finding.metadata == {"rule": "G1", "section": "", "source": "REVIEW.md"}
    assert result.summary == "Breaks 1 of 2 rules in REVIEW.md."


def test_quotes_match_ignoring_case_and_spacing(monkeypatch):
    _answer(monkeypatch, {"rule": "G1", "quote": "LINE 4 HAS INCONSISTENT  indentation"})
    assert not g.check_guidelines(OUTPUT, RULES).passed


def test_unknown_rules_missing_quotes_short_quotes_and_repeats_are_discarded(monkeypatch):
    _answer(
        monkeypatch,
        {"rule": "G9", "quote": "has inconsistent indentation"},
        {"rule": "G2", "quote": "the function is not named"},
        {"rule": "G2", "quote": ""},
        {"rule": "G1", "quote": "reformat"},
        {"rule": "g1 ", "quote": "inconsistent indentation; please reformat"},
        {"rule": "G1", "quote": "has inconsistent indentation"},
    )
    result = g.check_guidelines(OUTPUT, RULES)
    assert [(f.metadata["rule"], f.evidence) for f in result.findings] == [
        ("G1", "inconsistent indentation; please reformat")
    ]
    assert result.metadata["discarded"] == 5


def test_a_short_output_can_be_quoted_whole(monkeypatch):
    _answer(monkeypatch, {"rule": "G1", "quote": "Reformat this."})
    assert not g.check_guidelines(
        ReviewOutput(output_type="issue", text="Reformat this."), RULES
    ).passed


def test_a_break_hides_a_miss_of_the_same_rule_in_either_order(monkeypatch):
    miss = {"rule": "G1", "kind": "misses", "quote": "Line 4 has inconsistent"}
    brk = {"rule": "G1", "kind": "breaks", "quote": "has inconsistent indentation"}
    for order in ((miss, brk), (brk, miss)):
        _answer(monkeypatch, *order)
        result = g.check_guidelines(OUTPUT, RULES)
        assert not result.passed
        assert [f.verdict for f in result.findings] == ["breaks_guideline"]


def test_no_violations_passes(monkeypatch):
    _answer(monkeypatch)
    result = g.check_guidelines(OUTPUT, RULES)
    assert result.passed
    assert result.summary == "Follows all 2 rules in REVIEW.md."


def test_the_prompt_carries_rules_evidence_and_output(monkeypatch):
    seen = _answer(monkeypatch)
    question = ReviewOutput(output_type="canvas_answer", text="No.", question="Is the API changed?")
    g.check_guidelines(question, RULES, evidence="+def f(): pass")
    assert "G2: Name the function an issue is about." in seen["user"]
    assert "+def f(): pass" in seen["user"]
    assert "Question it answers: Is the API changed?" in seen["user"]
    assert seen["user"].endswith("Output to check:\nNo.")


def test_a_miss_is_a_warning_that_does_not_fail(monkeypatch):
    _answer(
        monkeypatch,
        {
            "rule": "G2",
            "kind": "misses",
            "quote": "Line 4 has inconsistent indentation",
            "reason": "No function named.",
        },
    )
    result = g.check_guidelines(OUTPUT, RULES)
    assert result.passed
    assert [(f.verdict, f.severity) for f in result.findings] == [
        ("misses_guideline", Severity.WARN)
    ]
    assert result.summary == "Misses 1 of 2 rules in REVIEW.md."


def test_breaks_and_misses_are_counted_apart(monkeypatch):
    _answer(
        monkeypatch,
        {"rule": "G1", "quote": "indentation; please reformat"},
        {"rule": "G2", "kind": "misses", "quote": "Line 4 has inconsistent"},
    )
    result = g.check_guidelines(OUTPUT, RULES)
    assert not result.passed
    assert result.summary == "Breaks 1 and misses 1 of 2 rules in REVIEW.md."


def test_the_prompt_tells_breaks_from_misses():
    assert "- breaks:" in g.CHECK_PROMPT and "- misses:" in g.CHECK_PROMPT


def test_the_prompt_keeps_accuracy_out_and_scopes_rules_by_section():
    assert "You do not judge whether it is accurate" in g.CHECK_PROMPT
    assert "never a break and never a miss" in g.CHECK_PROMPT
    assert "apply only to the kind of output that section names" in g.CHECK_PROMPT


def test_the_result_says_whether_the_rules_were_built_in(monkeypatch):
    from attest.code_review.guidelines import general_guidelines

    _answer(monkeypatch)
    assert g.check_guidelines(OUTPUT, general_guidelines()).metadata["builtin"] is True
    assert g.check_guidelines(OUTPUT, RULES).metadata["builtin"] is False


def test_an_unconfirmed_break_is_discarded(monkeypatch):
    _answer(monkeypatch, {"rule": "G1", "quote": "has inconsistent indentation"})
    monkeypatch.setattr(
        g,
        "confirm_break",
        lambda rule, output, quote: ConfirmOut(reports_code=True, reason="Describes code."),
    )
    result = g.check_guidelines(OUTPUT, RULES)
    assert result.passed
    assert result.findings == []
    assert result.metadata["unconfirmed"] == 1


def test_breaks_are_confirmed_and_misses_are_not(monkeypatch, confirmed):
    _answer(
        monkeypatch,
        {"rule": "G1", "quote": "has inconsistent indentation", "reason": "first look"},
        {"rule": "G2", "kind": "misses", "quote": "Line 4 has inconsistent"},
    )
    result = g.check_guidelines(OUTPUT, RULES)
    assert confirmed == [("G1", "has inconsistent indentation")]
    assert result.findings[0].reason == "Confirmed."


def test_the_confirm_prompt_says_describing_code_is_not_a_break():
    from attest.prompts.code_review.guidelines import CONFIRM_PROMPT

    assert "Reporting a problem is what reviewers are for" in CONFIRM_PROMPT
    assert "does_itself is always false" in CONFIRM_PROMPT
    assert "newly added lines are lines a pull request changes" in CONFIRM_PROMPT


@pytest.mark.parametrize(
    "answer, breaks",
    [
        ({"reports_code": True}, False),
        ({"reports_code": True, "approves_code": True}, True),
        ({"does_itself": True}, True),
        ({}, False),
    ],
)
def test_only_approving_or_doing_counts_as_a_break(answer, breaks):
    assert ConfirmOut(**answer).breaks is breaks
