"""Render attest's review of a pull request as a GitHub review body."""

from __future__ import annotations

from ..code_review import ReviewResult
from ..code_review.review import OutputDecision

MARKER = "<!-- attest-review -->"
MAX_BODY_CHARS = 60_000
"""GitHub refuses review bodies over 65,536 characters; leave room for the footer."""
DOCS_URL = "https://peace-orefejo.github.io/attest/github-action/"


def review_body(
    result: ReviewResult,
    *,
    head_sha: str,
    undiffed: list[str],
    rules: str | None,
) -> str:
    """The review: kept issues, the overview, per-file summaries, and anything to check by hand.

    Only outputs attest kept are shown; dropped ones are counted, never posted.
    """
    kept = [d for d in result.decisions if d.keep]
    issues = [d for d in kept if d.output_type == "issue"]
    overview = next((d for d in kept if d.output_type == "group_summary"), None)
    files = [d for d in kept if d.output_type == "diff_summary"]
    dropped = len(result.decisions) - len(kept)

    lines = [MARKER, "### attest review", ""]
    if overview is not None:
        lines += [overview.text.strip(), ""]
    if issues:
        lines += [f"**Issues ({len(issues)})**", ""]
        lines += [f"- {_where(d)}{_one_line(d.text)}" for d in issues]
    else:
        lines.append("**No issues** that the diff backs up.")
    lines.append("")
    if files:
        lines += ["<details><summary>What changed, file by file</summary>", ""]
        lines += [f"- {_where(d)}{_one_line(d.text)}" for d in files]
        lines += ["", "</details>", ""]
    notes = _notes(result, undiffed)
    if notes:
        lines += ["**Check by hand**", ""] + [f"- {note}" for note in notes] + [""]
    lines.append(_footer(len(result.decisions), dropped, head_sha, rules))
    return _fit("\n".join(lines))


def failure_body(why: str) -> str:
    """A short note for a person who asked for a review that couldn't be written."""
    return "\n".join(
        [
            MARKER,
            "### attest review",
            "",
            f"attest couldn't review this pull request: {_one_line(why)}",
            "",
            f"<sub>Nothing was checked. The workflow log has details. "
            f"[About attest reviews]({DOCS_URL})</sub>",
        ]
    )


def _where(decision: OutputDecision) -> str:
    return f"`{decision.paths[0]}`: " if len(decision.paths) == 1 else ""


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _notes(result: ReviewResult, undiffed: list[str]) -> list[str]:
    notes: list[str] = []
    if not result.injection.passed:
        notes.append(
            "This pull request contains text that looks aimed at AI reviewers. Comments it may "
            "have influenced were dropped; read the change yourself."
        )
    if undiffed:
        shown = ", ".join(f"`{path}`" for path in undiffed[:10])
        more = f" and {len(undiffed) - 10} more" if len(undiffed) > 10 else ""
        notes.append(f"GitHub sent no diff for {shown}{more} (binary or too large): not reviewed.")
    if result.excluded_files:
        notes.append(
            f"{len(result.excluded_files)} file(s) matched `.attestignore` and weren't reviewed."
        )
    return notes


def _footer(total: int, dropped: int, head_sha: str, rules: str | None) -> str:
    checked = f"attest wrote {total} comment(s) and checked each against the diff"
    held = f"; {dropped} didn't hold up and weren't posted." if dropped else "; all held up."
    used = f" Rules: `{rules}`." if rules else ""
    return (
        f"<sub>{checked}{held}{used} Reviewed at {head_sha[:7]}. "
        f"[About attest reviews]({DOCS_URL})</sub>"
    )


def _fit(body: str) -> str:
    if len(body) <= MAX_BODY_CHARS:
        return body
    return body[:MAX_BODY_CHARS].rsplit("\n", 1)[0] + "\n\n_(cut to fit GitHub's limit)_"
