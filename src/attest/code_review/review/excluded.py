"""Outputs about excluded files only: never graded, reported as unchecked, always dropped."""

from __future__ import annotations

from ...checks.claim_findings import unchecked
from ...exclusions import ATTESTIGNORE, EXCLUDED_REASON, Exclusions
from ...results import CheckResult, Report
from ..evidence import Omission
from ..models import PullRequest, ReviewOutput

EXCLUDED_SUBJECT_REASON = (
    f"Not checked: every file this output is about is {EXCLUDED_REASON}, "
    "so attest has no evidence for it."
)


def entirely_excluded(output: ReviewOutput, omissions: list[Omission]) -> bool:
    """True when the output names files and every one of them was excluded."""
    paths = output.paths()
    excluded = {omission.path for omission in omissions if omission.reason == "excluded"}
    return bool(paths) and all(path in excluded for path in paths)


def excluded_report(output: ReviewOutput, check: str) -> Report:
    """A faithfulness result with one unchecked finding, so the gate drops the output."""
    finding = unchecked(output.text, EXCLUDED_SUBJECT_REASON)
    finding.metadata["excluded"] = True
    result = CheckResult(
        check=check,
        passed=False,
        score=None,
        summary=EXCLUDED_SUBJECT_REASON,
        findings=[finding],
        metadata={"claims_checked": 0, "claims_unchecked": 1, "excluded_subject": True},
    )
    return Report(results=[result])


def exclusion_warnings(excluded: list[str], exclusions: Exclusions, pr: PullRequest) -> list[str]:
    """Say what was left unreviewed, and flag a pull request that edits its own exclusions."""
    warnings: list[str] = []
    if excluded:
        count = len(excluded)
        files = "file was" if count == 1 else "files were"
        warnings.append(
            f"{count} {files} {EXCLUDED_REASON} and not reviewed: their contents were left out "
            "of the evidence and the injection scan."
        )
    names = {_name(source) for source in exclusions.sources} | {ATTESTIGNORE}
    changed = {_name(path) for path in [*pr.diffs, *pr.changed_files]}
    warnings.extend(
        f"This pull request changes {name}, which exclusion patterns can be read from. "
        "Check the patterns came from the base branch, not the pull request."
        for name in sorted(names & changed)
        if exclusions.active
    )
    return warnings


def _name(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]
