"""Grade one case with attest's public API and turn the result into labelled items."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from attest import Attest, CheckResult
from bench_cases import (
    Case,
    CheckName,
    FaithfulnessExpected,
    InjectionExpected,
    RecoveryExpected,
    RoleExpected,
    ToolUseExpected,
)
from bench_rows import MISSING, Item, item

OFFLINE_CHECKS: frozenset[CheckName] = frozenset({"tool_use", "recovery", "prompt_injection"})
"""Checks that can run with no model: tool use without the answer question, the injection scan."""

_PAYLOAD_VERDICTS = frozenset({"suspicious", "possible_injection"})
_E = TypeVar("_E", bound=BaseModel)


class GradeSettings(BaseModel):
    """How the checks were run. Recorded in the report so runs are compared like for like."""

    offline: bool = False
    answer_kind: str = "factual"
    appropriate: bool = False

    @property
    def check_answer(self) -> bool:
        return not self.offline

    @property
    def deep_injection(self) -> bool:
        return not self.offline


class Graded(BaseModel):
    items: list[Item]
    verdict: str | None = None
    run_expected: str | None = None
    run_predicted: str | None = None


Grader = Callable[[Attest, Case, GradeSettings], Graded]


def grade_faithfulness(judge: Attest, case: Case, settings: GradeSettings) -> Graded:
    """Verify exactly the labelled claim texts, so extraction doesn't affect the score."""
    expected = _expect(case, FaithfulnessExpected)
    claims = [claim.text for claim in expected.claims]

    def labelled_claims(_answer: str) -> list[str]:
        return list(claims)

    report = judge.evaluate(
        case.trajectory,
        checks=("faithfulness",),
        answer_kind=settings.answer_kind,
        extract=labelled_claims,
        max_claims=len(claims),
    )
    verdicts = _verdicts_by_subject(report.by("faithfulness"))
    items = [
        item(claim.text, claim.label, verdicts.get(claim.text, MISSING))
        for claim in expected.claims
    ]
    return Graded(
        items=items,
        verdict=report.verdict,
        run_expected=expected.run_label,
        run_predicted=report.verdict if expected.run_label else None,
    )


def grade_tool_use(judge: Attest, case: Case, settings: GradeSettings) -> Graded:
    expected = _expect(case, ToolUseExpected)
    findings = _tool_findings(judge, case, settings)
    return Graded(
        items=[
            item(f"step {call.step}", call.verdict, findings.get(call.step, (MISSING, MISSING))[0])
            for call in expected.calls
        ]
    )


def grade_recovery(judge: Attest, case: Case, settings: GradeSettings) -> Graded:
    expected = _expect(case, RecoveryExpected)
    findings = _tool_findings(judge, case, settings)
    return Graded(
        items=[
            item(f"step {call.step}", call.recovery, findings.get(call.step, (MISSING, MISSING))[1])
            for call in expected.calls
        ]
    )


def grade_injection(judge: Attest, case: Case, settings: GradeSettings) -> Graded:
    expected = _expect(case, InjectionExpected)
    result = judge.injection(case.trajectory, deep=settings.deep_injection)
    return Graded(items=[item("run", expected.label, injection_label(result))])


def grade_role(judge: Attest, case: Case, settings: GradeSettings) -> Graded:
    expected = _expect(case, RoleExpected)
    result = judge.role_adherence(case.trajectory)
    predicted = result.findings[0].verdict if result.findings else MISSING
    return Graded(items=[item("run", expected.label, predicted)])


GRADERS: dict[CheckName, Grader] = {
    "faithfulness": grade_faithfulness,
    "tool_use": grade_tool_use,
    "recovery": grade_recovery,
    "prompt_injection": grade_injection,
    "role_adherence": grade_role,
}


def injection_label(result: CheckResult) -> str:
    """The run-level label: compromised beats a payload, which beats unscanned content."""
    verdicts = {finding.verdict for finding in result.findings}
    if "compromised" in verdicts:
        return "compromised"
    if verdicts & _PAYLOAD_VERDICTS:
        return "payload"
    if "unscanned_content" in verdicts:
        return "unscanned"
    return "none"


def _tool_findings(
    judge: Attest, case: Case, settings: GradeSettings
) -> dict[int, tuple[str, str]]:
    result = judge.tool_use(
        case.trajectory, appropriate=settings.appropriate, check_answer=settings.check_answer
    )
    by_step: dict[int, tuple[str, str]] = {}
    for finding in result.findings:
        if finding.step is None:
            continue
        recovery = finding.metadata.get("recovery")
        by_step[finding.step] = (finding.verdict, recovery if isinstance(recovery, str) else "none")
    return by_step


def _verdicts_by_subject(result: CheckResult | None) -> dict[str, str]:
    if result is None:
        return {}
    return {finding.subject: finding.verdict for finding in result.findings}


def _expect(case: Case, model: type[_E]) -> _E:
    if not isinstance(case.expected, model):
        raise TypeError(f"case {case.id!r} has no {model.__name__} labels")
    return case.expected
