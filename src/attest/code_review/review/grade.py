"""Grade one output against its evidence and, when asked, the team's review rules."""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple, TypeAlias

from ...results import Report
from ...trajectory import Trajectory
from ..adapter import to_run_with_omissions
from ..evidence import EvidenceLimits, Omission
from ..guidelines import ReviewGuidelines, check_guidelines
from ..models import ReviewOutput
from ..tool_names import READ_GUIDELINES

Evaluator: TypeAlias = Callable[[Trajectory], Report]
FAITHFULNESS_CHECK = "faithfulness"


class Graded(NamedTuple):
    report: Report
    omissions: list[Omission]


def grade(
    output: ReviewOutput,
    evaluate: Evaluator,
    rules: ReviewGuidelines,
    *,
    follow: bool,
    limits: EvidenceLimits | None,
) -> Graded:
    """Run `evaluate` on the output's evidence, adding the guideline check for the team's rules."""
    evidence_rules = None if rules.builtin else rules
    run, omissions = to_run_with_omissions(output, limits=limits, guidelines=evidence_rules)
    report = evaluate(run)
    if report.by(FAITHFULNESS_CHECK) is None:
        raise ValueError(
            "evaluate must return a report with a faithfulness result; "
            "without one no output can be checked against its evidence."
        )
    if follow and not rules.builtin:
        conformance = check_guidelines(output, rules, evidence=_code_evidence(run))
        report = Report(results=[*report.results, conformance], metadata=report.metadata)
    return Graded(report=report, omissions=omissions)


def _code_evidence(run: Trajectory) -> str:
    steps = [
        step for step in run.steps if not step.tool_call or step.tool_call.name != READ_GUIDELINES
    ]
    return run.model_copy(update={"steps": steps}).evidence()
