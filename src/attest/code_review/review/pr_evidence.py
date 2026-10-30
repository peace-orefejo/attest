"""Fill outputs from the pull request, and warn about what the review cannot vouch for."""

from __future__ import annotations

from pathlib import PurePosixPath

from ...results import CheckResult
from ..guidelines import ReviewGuidelines
from ..models import PullRequest, ReviewOutput

INCOMPLETE_SCAN_WARNING = (
    "The injection scan did not check every hit before its budget ran out; "
    "kept outputs may still have been steered by text the scan did not reach."
)


def with_pr_evidence(output: ReviewOutput, pr: PullRequest) -> ReviewOutput:
    """Give an output the pull request's diffs and changed files when it carries none of its own."""
    updates: dict[str, object] = {}
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
    if rules.builtin:
        return []
    changed = {
        PurePosixPath(path.replace("\\", "/")).name for path in [*pr.diffs, *pr.changed_files]
    }
    sources = sorted({rule.source for rule in rules.rules if rule.source})
    return [
        f"This pull request changes {source}, which the review rules were loaded from. "
        f"Check the rules came from the base branch, not the pull request."
        for source in sources
        if source in changed
    ]


def injection_warnings(injection: CheckResult) -> list[str]:
    """Warn when the injection scan could not cover the whole pull request."""
    return [INCOMPLETE_SCAN_WARNING] if injection.metadata.get("coverage_incomplete") else []
