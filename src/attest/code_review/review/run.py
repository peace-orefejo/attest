"""Check and gate every output of one pull request review in a single call."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePosixPath

from ...core import Report, Trajectory
from ..adapter import to_run_with_omissions
from ..evidence import EvidenceLimits
from ..gate import gate
from ..gate.defaults import DEFAULT_MODES
from ..guidelines import GuidelinesInput, ReviewGuidelines, check_guidelines, load_guidelines
from ..injection import check_code_injection
from ..models import GateMode, PullRequest, ReviewOutput
from ..tool_names import READ_GUIDELINES
from ..writer import write_review
from .models import OutputDecision, ReviewResult

Evaluator = Callable[[Trajectory], Report]


def with_pr_evidence(output: ReviewOutput, pr: PullRequest) -> ReviewOutput:
    """Give an output the pull request's diffs and changed files when it carries none of its own."""
    updates: dict = {}
    if not output.diffs and pr.diffs:
        if output.output_type == "diff_summary" and len(pr.diffs) > 1:
            raise ValueError(
                "A diff_summary describes one file, and this pull request changes several. "
                "Give the output its own diffs={path: diff}."
            )
        updates["diffs"] = dict(pr.diffs)
    if output.changed_files is None and pr.changed_files:
        updates["changed_files"] = list(pr.changed_files)
    return output.model_copy(update=updates) if updates else output


def guideline_warnings(rules: ReviewGuidelines, pr: PullRequest) -> list[str]:
    """Warn when the pull request changes a file the review rules came from."""
    changed = {PurePosixPath(path.replace("\\", "/")).name for path in [*pr.diffs, *pr.changed_files]}
    sources = sorted({rule.source for rule in rules.rules if rule.source} - {""})
    return [f"This pull request changes {source}, which the review rules were loaded from. "
            f"Check the rules came from the base branch, not the pull request."
            for source in sources if not rules.builtin and source in changed]


def _check_modes(modes: Mapping[str, GateMode]) -> None:
    unknown = sorted(set(modes) - set(DEFAULT_MODES))
    if unknown:
        raise ValueError(
            f"Unknown output type(s) in modes: {', '.join(unknown)}. "
            f"Choose from: {', '.join(DEFAULT_MODES)}."
        )


def _grade(output: ReviewOutput, evaluate: Evaluator, rules: ReviewGuidelines,
           follow: bool, limits: EvidenceLimits | None):
    evidence_rules = None if rules.builtin else rules
    run, omissions = to_run_with_omissions(output, limits=limits, guidelines=evidence_rules)
    report = evaluate(run)
    if follow and not rules.builtin:
        code_only = run.model_copy(update={"steps": [
            step for step in run.steps if not step.tool_call or step.tool_call.name != READ_GUIDELINES]})
        conformance = check_guidelines(output, rules, evidence=code_only.evidence())
        report = Report(results=[*report.results, conformance], metadata=report.metadata)
    return report, omissions


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
    """Scan the pull request for injection once, then grade and gate each output against its evidence.

    With no `outputs`, attest writes the review itself, following `guidelines`.
    `guidelines` are the team's review rules (markdown paths or text). They are evidence, so an
    issue citing one can be checked, and `follow_guidelines` drops outputs that break one. Without
    them, attest's own reviewer follows the built-in general standard, and outputs are checked
    for faithfulness only. Outputs without their own diffs or
    changed-file list use the pull request's. `evaluate` turns a run into a Report with a
    faithfulness result, and `modes` overrides the default gate mode per output type.
    """
    modes = dict(modes or {})
    _check_modes(modes)
    rules = load_guidelines(guidelines)
    written = outputs is None
    source = write_review(pr, guidelines=rules, limits=limits) if outputs is None else outputs
    filled = [with_pr_evidence(output, pr) for output in source]
    injection = check_code_injection(pr, filled, deep=deep)
    decisions: list[OutputDecision] = []
    for index, output in enumerate(filled):
        report, omissions = _grade(output, evaluate, rules, follow_guidelines, limits)
        decision = gate(report, output.output_type, mode=modes.get(output.output_type),
                        injection=injection, paths=output.paths(), output_index=index)
        faithfulness = report.by("faithfulness")
        decisions.append(OutputDecision(
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
            omissions=omissions,
        ))
    return ReviewResult(decisions=decisions, injection=injection, guidelines=rules, written=written,
                        warnings=guideline_warnings(rules, pr), outputs=list(source))
