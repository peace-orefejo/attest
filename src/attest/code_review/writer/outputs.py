"""Turn attest's written review into review outputs, each scoped to the diffs it is about."""

from __future__ import annotations

from ...utils.diff import parse_unified_diff
from ..models import PullRequest, ReviewOutput
from .models import WrittenIssue, WrittenReview, WrittenSummary

_DIFF_PREFIXES = ("./", "a/", "b/")


def to_outputs(written: WrittenReview, pr: PullRequest) -> list[ReviewOutput]:
    """Turn a written review into review outputs, each scoped to the diffs it is about.

    An issue keeps its line only when that line is an added or unchanged line of its file's
    diff, and its suggestion only when it keeps its line.
    """
    changed = list(pr.changed_files) or None
    outputs = [_issue(issue, pr, changed) for issue in written.issues if issue.text.strip()]
    for summary in written.summaries:
        output = summary_output(summary, pr)
        if output is not None:
            outputs.append(output)
    overview = overview_output(written.overview, pr)
    if overview is not None:
        outputs.append(overview)
    return outputs


def summary_output(summary: WrittenSummary, pr: PullRequest) -> ReviewOutput | None:
    """One file's summary, scoped to that file's diff; None for an empty one or unknown file."""
    path = _match(pr, summary.file)
    if not summary.text.strip() or path is None:
        return None
    return ReviewOutput(output_type="diff_summary", text=summary.text, diffs={path: pr.diffs[path]})


def overview_output(text: str, pr: PullRequest) -> ReviewOutput | None:
    """The overview, scoped to every diff; None when it is empty."""
    if not text.strip():
        return None
    return ReviewOutput(
        output_type="group_summary",
        text=text,
        diffs=dict(pr.diffs),
        changed_files=list(pr.changed_files) or None,
        group_name=pr.title or "pull request",
    )


def _issue(issue: WrittenIssue, pr: PullRequest, changed: list[str] | None) -> ReviewOutput:
    path = _match(pr, issue.file)
    line = issue.line if path is not None and _on_new_side(pr.diffs[path], issue.line) else None
    suggestion = issue.suggestion if line is not None and issue.suggestion is not None else None
    return ReviewOutput(
        output_type="issue",
        text=issue.text,
        diffs={path: pr.diffs[path]} if path else dict(pr.diffs),
        changed_files=changed,
        line=line,
        suggestion=suggestion,
    )


def _on_new_side(diff: str, line: int | None) -> bool:
    if line is None or line < 1:
        return False
    return any(
        row.new_no == line and row.kind in ("+", " ")
        for file_diff in parse_unified_diff(diff)
        for hunk in file_diff.hunks
        for row in hunk.lines
    )


def _match(pr: PullRequest, file: str) -> str | None:
    if file in pr.diffs:
        return file
    wanted = _norm_path(file)
    return next((path for path in pr.diffs if _norm_path(path) == wanted), None)


def _norm_path(path: str) -> str:
    path = path.strip().replace("\\", "/")
    for prefix in _DIFF_PREFIXES:
        if path.startswith(prefix):
            path = path[len(prefix) :]
    return path
