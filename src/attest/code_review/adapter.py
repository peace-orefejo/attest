"""Turn a code review output into an attest Trajectory whose tool calls are the evidence."""

from __future__ import annotations

from typing import NamedTuple

from ..exclusions import Exclusions, ExclusionsInput, as_exclusions
from ..trajectory import Step, ToolCall, Trajectory
from .evidence.excluded import changed_files_listing, hide_read
from .evidence.large_files import render_diffs
from .evidence.models import EvidenceLimits, Omission
from .evidence.scoping import Scope, read_label, scope_evidence
from .guidelines import ReviewGuidelines
from .models import FileRead, OutputType, ReviewOutput
from .tool_names import EVIDENCE_TOOLS, LIST_CHANGED_FILES, READ_DIFF, READ_GUIDELINES

_TASKS: dict[OutputType, str] = {
    "issue": "Review the diff and report bugs.",
    "diff_summary": "Summarise this diff.",
}
_NO_CHANGED_FILES = "(no files changed)"


class RunWithOmissions(NamedTuple):
    run: Trajectory
    omissions: list[Omission]


class _BoundedRead(NamedTuple):
    text: str
    omission: Omission | None


class _Steps(NamedTuple):
    steps: list[Step]
    omissions: list[Omission]


def task_text(output: ReviewOutput) -> str:
    """Return the run's task text for an output type."""
    if output.output_type == "group_summary":
        name = output.group_name
        return f'Summarise the group "{name}".' if name else "Summarise the group."
    if output.output_type == "canvas_answer":
        return output.question or ""
    return _TASKS[output.output_type]


def to_run_with_omissions(
    output: ReviewOutput,
    *,
    limits: EvidenceLimits | None = None,
    guidelines: ReviewGuidelines | None = None,
    exclude: ExclusionsInput = None,
) -> RunWithOmissions:
    """Build the run for a review output and list which files had content left out and why.

    `guidelines`, when given, are added as a read_guidelines step so claims citing a rule
    can be checked. Files that `exclude` names appear only as one-line notes, with an
    `excluded` omission each.
    """
    limits = limits or EvidenceLimits()
    scope = scope_evidence(output)
    built = _evidence_steps(scope, limits, as_exclusions(exclude))
    steps = built.steps
    if guidelines is not None:
        steps.append(_step(READ_GUIDELINES, {"name": guidelines.name}, guidelines.render()))
    omissions = [
        *built.omissions,
        *(_out_of_scope(path) for path in scope.dropped_diffs),
        *(_out_of_scope(read_label(read)) for read in scope.dropped_reads),
    ]
    run = Trajectory(
        task=task_text(output),
        allowed_tools=list(EVIDENCE_TOOLS),
        steps=steps,
        final_answer=output.text,
    )
    return RunWithOmissions(run=run, omissions=omissions)


def to_run(
    output: ReviewOutput,
    *,
    limits: EvidenceLimits | None = None,
    guidelines: ReviewGuidelines | None = None,
    exclude: ExclusionsInput = None,
) -> Trajectory:
    """Build the run for a review output; evidence comes only from tool calls."""
    return to_run_with_omissions(output, limits=limits, guidelines=guidelines, exclude=exclude).run


def _evidence_steps(scope: Scope, limits: EvidenceLimits, exclusions: Exclusions) -> _Steps:
    steps: list[Step] = []
    omissions: list[Omission] = []
    if scope.changed_files is not None:
        listing = "\n".join(changed_files_listing(scope.changed_files, exclusions))
        steps.append(_step(LIST_CHANGED_FILES, {}, listing or _NO_CHANGED_FILES))
    for item in render_diffs(scope.diffs, limits, exclusions):
        steps.append(_step(READ_DIFF, {"path": item.path}, item.text))
        if item.omission is not None:
            omissions.append(item.omission)
    for original in scope.reads:
        hidden = hide_read(original, exclusions)
        read = hidden.read
        omissions.extend(Omission(path=path, reason="excluded") for path in hidden.excluded)
        bounded = _bounded_read(read, limits)
        steps.append(_step(read.tool, dict(read.arguments), bounded.text))
        if bounded.omission is not None:
            omissions.append(bounded.omission)
    return _Steps(steps=steps, omissions=omissions)


def _bounded_read(read: FileRead, limits: EvidenceLimits) -> _BoundedRead:
    if len(read.output) <= limits.max_file_chars:
        return _BoundedRead(text=read.output, omission=None)
    label = read_label(read)
    note = f"[{label}: output cut at {limits.max_file_chars} characters; the rest was omitted]"
    kept = read.output[: limits.max_file_chars]
    return _BoundedRead(text=f"{kept}\n{note}", omission=Omission(path=label, reason="truncated"))


def _step(name: str, arguments: dict[str, object], output: str) -> Step:
    return Step(tool_call=ToolCall(name=name, arguments=arguments, output=output))


def _out_of_scope(path: str) -> Omission:
    return Omission(path=path, reason="out_of_scope")
