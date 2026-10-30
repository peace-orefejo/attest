"""Turn attest's written review into review outputs, each scoped to the diffs it is about."""

from __future__ import annotations

from ..models import PullRequest, ReviewOutput
from .models import WrittenReview

_DIFF_PREFIXES = ("./", "a/", "b/")


def to_outputs(written: WrittenReview, pr: PullRequest) -> list[ReviewOutput]:
    """Turn a written review into review outputs, each scoped to the diffs it is about."""
    changed = list(pr.changed_files) or None
    outputs = [
        ReviewOutput(
            output_type="issue",
            text=issue.text,
            diffs=_diffs_for(pr, issue.file),
            changed_files=changed,
        )
        for issue in written.issues
        if issue.text.strip()
    ]
    for summary in written.summaries:
        path = _match(pr, summary.file)
        if summary.text.strip() and path:
            outputs.append(
                ReviewOutput(
                    output_type="diff_summary", text=summary.text, diffs={path: pr.diffs[path]}
                )
            )
    if written.overview.strip():
        outputs.append(
            ReviewOutput(
                output_type="group_summary",
                text=written.overview,
                diffs=dict(pr.diffs),
                changed_files=changed,
                group_name=pr.title or "pull request",
            )
        )
    return outputs


def _diffs_for(pr: PullRequest, file: str) -> dict[str, str]:
    path = _match(pr, file)
    return {path: pr.diffs[path]} if path else dict(pr.diffs)


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
