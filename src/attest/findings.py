"""One call for review bots: check findings against a diff and get keep or drop with a reason."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from .api import Attest
from .code_review import PullRequest, ReviewOutput
from .code_review.guidelines import GuidelinesInput
from .code_review.review import OutputDecision
from .providers import DEFAULT_PROVIDER
from .results import Finding

_GIT_HEADER = "diff --git "
_QUOTED_PATH = re.compile(r'^"(.*)"$')


class CheckedFinding(BaseModel):
    """One finding or answer, and whether the diff supports it."""

    text: str
    question: str | None = None
    """The question, when this is an answer to one."""
    keep: bool
    """True when the diff backs it up. Post it only then."""
    reason: str
    """Why, in one line: what the check found, or what dropped it."""
    reasons: list[str] = Field(default_factory=list[str])
    """Every finding that dropped it, one line each. Empty when kept."""


def check_findings(
    diff: str | Mapping[str, str],
    findings: Sequence[str] = (),
    *,
    answers: Mapping[str, str] | None = None,
    guidelines: GuidelinesInput = None,
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    key: str | None = None,
    attest: Attest | None = None,
) -> list[CheckedFinding]:
    """Check what an AI reviewer said about a change against the change itself.

    `diff` is the output of `git diff` (or a `{path: diff}` mapping). `findings` are the
    reviewer's comments; `answers` maps each question asked about the change to the reviewer's
    answer. Returns one `CheckedFinding` per finding, then one per answer, in order.

    Findings are kept unless the diff contradicts them. Answers are held to a stricter bar: kept
    only when the diff clearly backs them. Pass `guidelines` (your review rules, as markdown text
    or a path) to also drop anything that breaks them. Pass an `Attest` to choose every other
    setting; otherwise one is built from `provider`, `model` and `key` (or the usual environment
    variable). Needs a model key, like every check that calls a model.
    """
    answers = dict(answers or {})
    if not findings and not answers:
        raise ValueError("Pass at least one finding or answer to check.")
    if isinstance(findings, str):
        raise TypeError("findings is a list of comments; wrap a single one in a list.")
    diffs = split_diff(diff) if isinstance(diff, str) else dict(diff)
    if not diffs:
        raise ValueError("The diff is empty: there is nothing to check the findings against.")
    outputs = [ReviewOutput(output_type="issue", text=text) for text in findings]
    outputs += [
        ReviewOutput(output_type="canvas_answer", text=answer, question=question)
        for question, answer in answers.items()
    ]
    judge = attest or Attest(key, provider=provider, model=model)
    result = judge.review(
        PullRequest(diffs=diffs, changed_files=list(diffs)),
        outputs,
        guidelines=guidelines,
        follow_guidelines=guidelines is not None,
    )
    return [_checked(decision) for decision in result.decisions]


def split_diff(text: str) -> dict[str, str]:
    """Split a multi-file unified diff, such as `git diff` output, into `{path: diff}`.

    Raises ValueError when no file header names a path, since then the findings can't be
    matched to files.
    """
    chunks: list[list[str]] = []
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not chunks or _starts_file(lines, index, chunks[-1]):
            chunks.append([])
        chunks[-1].append(line)
    diffs: dict[str, str] = {}
    for chunk in chunks:
        if not "".join(chunk).strip():
            continue
        path = _chunk_path(chunk)
        if path is None and not any(line.startswith("@@") for line in chunk):
            continue
        if path is None:
            raise ValueError(
                "Could not find a file name in the diff. Pass the full `git diff` output "
                "(with its `diff --git` or `---`/`+++` lines), or a {path: diff} mapping."
            )
        diffs[path] = diffs.get(path, "") + "".join(chunk)
    return diffs


def _starts_file(lines: list[str], index: int, current: list[str]) -> bool:
    line = lines[index]
    if line.startswith(_GIT_HEADER):
        return True
    if not (line.startswith("--- ") and index + 1 < len(lines)):
        return False
    if not lines[index + 1].startswith("+++ "):
        return False
    if index + 2 < len(lines) and not lines[index + 2].startswith("@@"):
        return False
    # A `---`/`+++` pair right after its own `diff --git` header belongs to that file.
    return not any(prior.startswith(_GIT_HEADER) for prior in current) or any(
        prior.startswith("@@") for prior in current
    )


def _chunk_path(chunk: list[str]) -> str | None:
    old = new = git = None
    for line in chunk:
        if line.startswith("+++ ") and new is None:
            new = _header_path(line[4:])
        elif line.startswith("--- ") and old is None:
            old = _header_path(line[4:])
        elif line.startswith(_GIT_HEADER) and git is None:
            git = _git_path(line[len(_GIT_HEADER) :])
        elif line.startswith("@@"):
            break
    for path in (new, old, git):
        if path and path != "/dev/null":
            return path
    return None


def _header_path(rest: str) -> str:
    path = rest.rstrip("\r\n").split("\t", 1)[0].strip()
    path = _QUOTED_PATH.sub(r"\1", path)
    return path[2:] if path.startswith(("a/", "b/")) else path


def _git_path(rest: str) -> str | None:
    rest = rest.rstrip("\r\n")
    marker = rest.rfind(" b/")
    if marker == -1:
        return None
    return rest[marker + 3 :] or None


def _checked(decision: OutputDecision) -> CheckedFinding:
    reasons = [_line(finding) for finding in decision.reasons]
    if decision.keep:
        reason = decision.summary or "Nothing in the diff contradicts it."
    elif reasons:
        extra = len(reasons) - 1
        reason = reasons[0] + (f" (and {extra} more)" if extra else "")
    else:
        reason = "Dropped: " + (decision.summary or "it could not be checked.")
    return CheckedFinding(
        text=decision.text,
        question=decision.question,
        keep=decision.keep,
        reason=reason,
        reasons=reasons,
    )


def _line(finding: Finding) -> str:
    what = finding.verdict.replace("_", " ")
    subject = finding.subject.strip()
    line = f"{what}: {subject}" if subject else what
    reason = finding.reason.strip()
    return f"{line} ({reason})" if reason else line
