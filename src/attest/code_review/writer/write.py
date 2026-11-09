"""write_review: attest's own reviewer, following the given guidelines or the general standard.

It writes in three steps, each building on the last, the way a careful reviewer works:

1. Understand: what each changed file now does.
2. Design: what the change does as a whole, and where the approach is risky.
3. Findings: the concrete problems, each on its line, with a one-line fix where there is one.

Every step reads the same evidence (rules, pull request, diffs), sent once as a cacheable prefix.
With `check`, each summary and the overview are checked before the next step builds on them, so
a misreading of the code is not carried forward.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TypeVar

from ...exclusions import Exclusions, ExclusionsInput, as_exclusions
from ...llm import call
from ...prompts.code_review.writer import (
    DESIGN_PROMPT,
    FINDINGS_PROMPT,
    UNDERSTAND_PROMPT,
    WRITE_PROMPT,
    findings_user,
    understanding_user,
    write_user,
)
from ..evidence import EvidenceLimits, render_diffs
from ..evidence.excluded import changed_files_listing, hide_pull_request
from ..guidelines import GuidelinesInput, ReviewGuidelines, general_guidelines, load_guidelines
from ..models import PullRequest, ReviewOutput
from .models import Design, Findings, Understanding, WrittenIssue, WrittenReview, WrittenSummary
from .outputs import overview_output, summary_output, to_outputs

MAX_TITLE_CHARS = 500
MAX_DESCRIPTION_CHARS = 10_000

Check = Callable[[ReviewOutput], bool]
"""Whether an output holds up against its evidence; failing ones are not built on."""

__all__ = [
    "MAX_DESCRIPTION_CHARS",
    "MAX_TITLE_CHARS",
    "WRITE_PROMPT",
    "Check",
    "WrittenIssue",
    "WrittenReview",
    "WrittenSummary",
    "write_review",
]

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def write_review(
    pr: PullRequest,
    *,
    guidelines: GuidelinesInput = None,
    limits: EvidenceLimits | None = None,
    exclude: ExclusionsInput = None,
    check: Check | None = None,
) -> list[ReviewOutput]:
    """Review a pull request: issues, one summary per changed file, and an overview.

    Files that `exclude` names reach the writer only as one-line notes, and the outputs carry
    those notes in place of their diffs. With `check`, only summaries and an overview that pass
    it are given to the later steps; every output is still returned, for the caller to gate.
    """
    if not pr.diffs:
        raise ValueError("The pull request has no diffs to review.")
    rules = load_guidelines(guidelines)
    exclusions = as_exclusions(exclude)
    visible = hide_pull_request(pr, exclusions).pr
    evidence = _evidence(visible, rules, limits, exclusions)
    passes: Check = check or _always

    understanding = _step(UNDERSTAND_PROMPT, evidence, "", Understanding)
    checked: list[tuple[str, str]] = []
    for summary in understanding.summaries:
        scoped = summary_output(summary, visible)
        if scoped is not None and passes(scoped):
            checked.append((next(iter(scoped.diffs)), summary.text))
    design = _step(DESIGN_PROMPT, evidence, understanding_user(checked), Design)
    overview = overview_output(design.overview, visible)
    kept_overview = design.overview if overview is not None and passes(overview) else ""
    findings = _step(FINDINGS_PROMPT, evidence, findings_user(checked, kept_overview), Findings)
    written = WrittenReview(
        issues=findings.issues, summaries=understanding.summaries, overview=design.overview
    )
    return to_outputs(written, visible)


_Step = TypeVar("_Step", Understanding, Design, Findings)


def _step(system: str, evidence: str, user: str, output: type[_Step]) -> _Step:
    return call(
        system=system,
        prefix=evidence,
        user=user or "Do step 1 now.",
        output=output,
        max_tokens=8192,
        reuse="prefix",
        site="writer",
    )


def _always(_output: ReviewOutput) -> bool:
    return True


def _evidence(
    pr: PullRequest,
    guidelines: ReviewGuidelines,
    limits: EvidenceLimits | None,
    exclusions: Exclusions,
) -> str:
    rendered = render_diffs(list(pr.diffs.items()), limits, exclusions)
    changed = changed_files_listing(pr.changed_files or list(pr.diffs), exclusions)
    return write_user(
        baseline=general_guidelines().render(),
        team_name=None if guidelines.builtin else guidelines.name,
        team_rules="" if guidelines.builtin else guidelines.render(),
        title=_cut(pr.title, MAX_TITLE_CHARS),
        description=_cut(pr.description, MAX_DESCRIPTION_CHARS),
        changed_files="\n".join(changed),
        diffs=[(item.path, number_lines(item.text)) for item in rendered],
    )


def number_lines(diff: str) -> str:
    """Put each added or unchanged line's new-file line number before it, for the reviewer.

    Text outside a hunk (headers, notes for cut or excluded files) is left as it is.
    """
    out: list[str] = []
    line_no: int | None = None
    for raw in diff.splitlines():
        hunk = _HUNK.match(raw)
        if hunk:
            line_no = int(hunk.group(1))
            out.append(raw)
        elif line_no is not None and raw[:1] in ("+", " ") and not raw.startswith("+++ "):
            out.append(f"{line_no:>5} {raw}")
            line_no += 1
        elif line_no is not None and raw[:1] == "-" and not raw.startswith("--- "):
            out.append(f"      {raw}")
        else:
            if raw.startswith(("--- ", "diff --git")):
                line_no = None
            out.append(raw)
    return "\n".join(out) + ("\n" if diff.endswith("\n") else "")


def _cut(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]} [cut at {max_chars} characters]"
