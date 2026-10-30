"""write_review: attest's own reviewer, following the given guidelines or the general standard."""

from __future__ import annotations

from ...llm import call
from ...prompts.code_review.writer import WRITE_PROMPT, write_user
from ..evidence import EvidenceLimits, render_diffs
from ..guidelines import GuidelinesInput, ReviewGuidelines, general_guidelines, load_guidelines
from ..models import PullRequest, ReviewOutput
from .models import WrittenIssue, WrittenReview, WrittenSummary
from .outputs import to_outputs

MAX_TITLE_CHARS = 500
MAX_DESCRIPTION_CHARS = 10_000

__all__ = [
    "MAX_DESCRIPTION_CHARS",
    "MAX_TITLE_CHARS",
    "WrittenIssue",
    "WrittenReview",
    "WrittenSummary",
    "write_review",
]


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
    written = call(
        system=WRITE_PROMPT, user=_user(pr, rules, limits), output=WrittenReview, max_tokens=8192
    )
    return to_outputs(written, pr)


def _user(pr: PullRequest, guidelines: ReviewGuidelines, limits: EvidenceLimits | None) -> str:
    rendered = render_diffs(list(pr.diffs.items()), limits)
    return write_user(
        baseline=general_guidelines().render(),
        team_name=None if guidelines.builtin else guidelines.name,
        team_rules="" if guidelines.builtin else guidelines.render(),
        title=_cut(pr.title, MAX_TITLE_CHARS),
        description=_cut(pr.description, MAX_DESCRIPTION_CHARS),
        changed_files="\n".join(pr.changed_files or list(pr.diffs)),
        diffs=[(item.path, item.text) for item in rendered],
    )


def _cut(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]} [cut at {max_chars} characters]"
