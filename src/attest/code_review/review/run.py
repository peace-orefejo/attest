"""Check and gate every output of one pull request review in a single call."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..evidence import EvidenceLimits
from ..gate import gate
from ..gate.defaults import DEFAULT_MODES
from ..guidelines import GuidelinesInput, load_guidelines
from ..injection import check_code_injection
from ..models import GateDecision, GateMode, PullRequest, ReviewOutput
from ..writer import write_review
from .grade import FAITHFULNESS_CHECK, Evaluator, Graded, grade
from .models import OutputDecision, ReviewResult
from .pr_evidence import guideline_warnings, injection_warnings, with_pr_evidence


def review(
    pr: PullRequest,
    outputs: Sequence[ReviewOutput] | None = None,
    *,
    evaluate: Evaluator,
    guidelines: GuidelinesInput = None,
    follow_guidelines: bool = True,
    modes: Mapping[str, GateMode] | None = None,
    deep: bool = True,
    limits: EvidenceLimits | None = None,
) -> ReviewResult:
    """Scan the pull request for injection once, then grade and gate each output on its evidence.

    With no `outputs`, attest writes the review itself, following `guidelines`.
    `guidelines` are the team's review rules (markdown paths or text). They are evidence, so an
    issue citing one can be checked, and `follow_guidelines` drops outputs that break one. Without
    them, attest's own reviewer follows the built-in general standard, and outputs are checked
    for faithfulness only. Outputs without their own diffs or
    changed-file list use the pull request's. `evaluate` turns a run into a Report with a
    faithfulness result, and `modes` overrides the default gate mode per output type.
    """
    chosen: dict[str, GateMode] = dict(modes) if modes else {}
    _check_modes(chosen)
    rules = load_guidelines(guidelines)
    source = write_review(pr, guidelines=rules, limits=limits) if outputs is None else outputs
    filled = [with_pr_evidence(output, pr) for output in source]
    injection = check_code_injection(pr, filled, deep=deep)
    decisions: list[OutputDecision] = []
    for index, output in enumerate(filled):
        graded = grade(output, evaluate, rules, follow=follow_guidelines, limits=limits)
        decision = gate(
            graded.report,
            output.output_type,
            mode=chosen.get(output.output_type),
            injection=injection,
            paths=output.paths(),
            output_index=index,
        )
        decisions.append(_decision(index, output, graded, decision))
    return ReviewResult(
        decisions=decisions,
        injection=injection,
        guidelines=rules,
        written=outputs is None,
        warnings=[*guideline_warnings(rules, pr), *injection_warnings(injection)],
        outputs=list(source),
    )


def _check_modes(modes: Mapping[str, GateMode]) -> None:
    unknown = sorted(set(modes) - set(DEFAULT_MODES))
    if unknown:
        raise ValueError(
            f"Unknown output type(s) in modes: {', '.join(unknown)}. "
            f"Choose from: {', '.join(DEFAULT_MODES)}."
        )


def _decision(
    index: int, output: ReviewOutput, graded: Graded, decision: GateDecision
) -> OutputDecision:
    faithfulness = graded.report.by(FAITHFULNESS_CHECK)
    return OutputDecision(
        index=index,
        output_type=output.output_type,
        text=output.text,
        question=output.question,
        paths=output.paths(),
        keep=decision.keep,
        mode=decision.mode,
        score=faithfulness.score if faithfulness else None,
        summary=faithfulness.summary if faithfulness else "",
        reasons=decision.reasons,
        notes=decision.notes,
        omissions=graded.omissions,
    )
