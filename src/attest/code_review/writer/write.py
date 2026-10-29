"""write_review: attest's own reviewer, following the given guidelines or the general standard."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...core.llm import call
from ..evidence import EvidenceLimits, render_diffs
from ..guidelines import GuidelinesInput, ReviewGuidelines, general_guidelines, load_guidelines
from ..models import PullRequest, ReviewOutput
from .prompts import WRITE_PROMPT


class WrittenIssue(BaseModel):
    file: str
    text: str


class WrittenSummary(BaseModel):
    file: str
    text: str


class WrittenReview(BaseModel):
    issues: list[WrittenIssue] = Field(default_factory=list)
    summaries: list[WrittenSummary] = Field(default_factory=list)
    overview: str = ""


def _prompt(pr: PullRequest, guidelines: ReviewGuidelines, limits: EvidenceLimits | None) -> str:
    diffs = "\n\n".join(f"### {item.path}\n{item.text}" for item in render_diffs(list(pr.diffs.items()), limits))
    about = "".join(
        f"{label}: {value}\n" for label, value in (("Title", pr.title), ("Description", pr.description)) if value
    )
    files = "\n".join(pr.changed_files or list(pr.diffs))
    rules = f"Baseline standard:\n{general_guidelines().render()}\n\n"
    if not guidelines.builtin:
        rules += f"Team rules ({guidelines.name}):\n{guidelines.render()}\n\n"
    return f"{rules}{about}Changed files:\n{files}\n\nDiffs:\n{diffs}"


def _norm_path(path: str) -> str:
    path = path.strip().replace("\\", "/")
    for prefix in ("./", "a/", "b/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
    return path


def _match(pr: PullRequest, file: str) -> str | None:
    if file in pr.diffs:
        return file
    wanted = _norm_path(file)
    return next((path for path in pr.diffs if _norm_path(path) == wanted), None)


def _diffs_for(pr: PullRequest, file: str) -> dict[str, str]:
    path = _match(pr, file)
    return {path: pr.diffs[path]} if path else dict(pr.diffs)


def to_outputs(written: WrittenReview, pr: PullRequest) -> list[ReviewOutput]:
    """Turn a written review into review outputs, each scoped to the diffs it is about."""
    changed = list(pr.changed_files) or None
    outputs = [ReviewOutput(output_type="issue", text=issue.text, diffs=_diffs_for(pr, issue.file),
                            changed_files=changed)
               for issue in written.issues if issue.text.strip()]
    for summary in written.summaries:
        path = _match(pr, summary.file)
        if summary.text.strip() and path:
            outputs.append(ReviewOutput(output_type="diff_summary", text=summary.text, diffs={path: pr.diffs[path]}))
    if written.overview.strip():
        outputs.append(ReviewOutput(output_type="group_summary", text=written.overview,
                                    diffs=dict(pr.diffs), changed_files=changed,
                                    group_name=pr.title or "pull request"))
    return outputs


def write_review(
    pr: PullRequest,
    *,
    guidelines: GuidelinesInput = None,
    limits: EvidenceLimits | None = None,
) -> list[ReviewOutput]:
    """Review a pull request: issues, one summary per changed file, and an overview."""
    if not pr.diffs:
        raise ValueError("The pull request has no diffs to review.")
    rules = load_guidelines(guidelines)
    written = call(system=WRITE_PROMPT, user=_prompt(pr, rules, limits), output=WrittenReview, max_tokens=8192)
    return to_outputs(written, pr)
