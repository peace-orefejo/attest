"""Check and gate every output of one pull request review in a single call."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from ...disposition_rules import is_unjudged
from ...exclusions import Exclusions, ExclusionsInput, as_exclusions
from ...llm import BudgetExceeded, ProviderConfigError
from ...results import CheckResult
from ...utils.failures import failure_reason
from ..evidence import EvidenceLimits
from ..evidence.excluded import hide_output, hide_pull_request, without_excluded_diffs
from ..gate import gate
from ..gate.defaults import DEFAULT_MODES
from ..guidelines import GUIDELINES_CHECK, GuidelinesInput, ReviewGuidelines, load_guidelines
from ..injection import check_code_injection
from ..models import GateDecision, GateMode, PullRequest, ReviewOutput
from ..writer import write_review
from ..writer.write import Check
from .excluded import exclusion_warnings
from .grade import FAITHFULNESS_CHECK, Evaluator, Graded, grade
from .models import OutputDecision, ReviewResult
from .pr_evidence import (
    guideline_warnings,
    injection_warnings,
    unchecked_guideline_warnings,
    with_pr_evidence,
    writer_warnings,
)


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
    exclude: ExclusionsInput = None,
) -> ReviewResult:
    """Scan the pull request for injection once, then grade and gate each output on its evidence.

    With no `outputs`, attest writes the review itself, following `guidelines`; if that call
    fails, the result has no decisions and a warning says why.
    `guidelines` are the team's review rules (markdown paths or text). They are evidence, so an
    issue citing one can be checked, and `follow_guidelines` drops outputs that break one. Without
    them, attest's own reviewer follows the built-in general standard, and outputs are checked
    for faithfulness only. Outputs without their own diffs or
    changed-file list use the pull request's. `evaluate` turns a run into a Report with a
    faithfulness result, and `modes` overrides the default gate mode per output type.
    An output whose check against your rules couldn't run, or with a reported break that couldn't
    be confirmed, is dropped in every mode, and a warning names it.

    `exclude` takes gitignore-style patterns (or an `Exclusions`). Excluded files' contents
    never reach a model or the injection scan; each appears as a one-line note, and an output
    about excluded files only is dropped as unchecked. `excluded_files` lists them.
    """
    chosen: dict[str, GateMode] = dict(modes) if modes else {}
    _check_modes(chosen)
    exclusions = as_exclusions(exclude)
    rules = load_guidelines(guidelines)
    hidden_pr = hide_pull_request(pr, exclusions)
    visible = hidden_pr.pr
    graded_once: dict[str, Graded] = {}

    def grade_once(output: ReviewOutput) -> Graded:
        key = output.model_dump_json()
        if key not in graded_once:
            graded_once[key] = grade(
                output,
                evaluate,
                rules,
                follow=follow_guidelines,
                limits=limits,
                exclusions=exclusions,
            )
        return graded_once[key]

    def holds_up(output: ReviewOutput) -> bool:
        """The writer's check between steps; the grade is reused when the output is gated."""
        filled = hide_output(with_pr_evidence(output, visible), exclusions).output
        mode = chosen.get(filled.output_type)
        return gate(grade_once(filled).report, filled.output_type, mode=mode).keep

    written = _write(visible, rules, limits, exclusions, holds_up) if outputs is None else None
    source = written.outputs if written is not None else outputs or []
    hidden = [hide_output(with_pr_evidence(output, visible), exclusions) for output in source]
    filled = [item.output for item in hidden]
    injection = _scan(visible, filled, exclusions, deep=deep)
    excluded = _union(hidden_pr.excluded, *(item.excluded for item in hidden))
    named_only = _union(hidden_pr.named_only, *(item.named_only for item in hidden))
    decisions: list[OutputDecision] = []
    unchecked: list[int] = []
    for index, output in enumerate(filled):
        graded = grade_once(output)
        if _rules_unchecked(graded):
            unchecked.append(index)
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
        writer_failure=written.failure if written else None,
        warnings=[
            *writer_warnings(written.failure if written else None),
            *guideline_warnings(rules, pr),
            *unchecked_guideline_warnings(unchecked, rules),
            *injection_warnings(injection),
            *exclusion_warnings(excluded, exclusions, pr, named_only),
        ],
        excluded_files=excluded,
        outputs=list(source),
    )


def _scan(
    pr: PullRequest, outputs: list[ReviewOutput], exclusions: Exclusions, *, deep: bool
) -> CheckResult:
    scanned = without_excluded_diffs(pr, exclusions)
    result = check_code_injection(scanned, outputs, deep=deep)
    skipped = [path for path in pr.diffs if path not in scanned.diffs]
    if skipped:
        result.metadata["files_excluded"] = list(skipped)
    return result


def _union(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(path for group in groups for path in group))


class _Written(BaseModel):
    outputs: list[ReviewOutput] = Field(default_factory=list[ReviewOutput])
    failure: str | None = None


def _write(
    pr: PullRequest,
    rules: ReviewGuidelines,
    limits: EvidenceLimits | None,
    exclusions: Exclusions,
    check: Check,
) -> _Written:
    """attest's own review, or why it wrote none; a failed call never aborts the review."""
    if not pr.diffs:
        raise ValueError("The pull request has no diffs to review.")
    try:
        written = write_review(pr, guidelines=rules, limits=limits, exclude=exclusions, check=check)
        return _Written(outputs=written)
    except (BudgetExceeded, ProviderConfigError):
        raise
    except Exception as error:
        return _Written(failure=failure_reason("Writing the review", error))


def _rules_unchecked(graded: Graded) -> bool:
    result = graded.report.by(GUIDELINES_CHECK)
    return result is not None and any(is_unjudged(f) for f in result.findings)


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
        line=output.line,
        suggestion=output.suggestion,
        paths=output.paths(),
        keep=decision.keep,
        mode=decision.mode,
        score=faithfulness.score if faithfulness else None,
        summary=faithfulness.summary if faithfulness else "",
        reasons=decision.reasons,
        notes=decision.notes,
        omissions=graded.omissions,
    )
