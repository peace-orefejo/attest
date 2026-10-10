"""Turn a code review pipeline output into an attest Trajectory whose tool calls are the evidence."""

from __future__ import annotations

from ..core import Step, ToolCall, Trajectory
from .evidence.large_files import EvidenceLimits, Omission, render_diffs
from .evidence.scoping import read_label, scope_evidence
from .models import ReviewOutput
from .tool_names import EVIDENCE_TOOLS, LIST_CHANGED_FILES, READ_DIFF

_TASKS = {
    "issue": "Review the diff and report bugs.",
    "diff_summary": "Summarise this diff.",
}
_NO_CHANGED_FILES = "(no files changed)"


def task_text(output: ReviewOutput) -> str:
    """Return the run's task text for an output type."""
    if output.output_type == "group_summary":
        name = output.group_name
        return f'Summarise the group "{name}".' if name else "Summarise the group."
    if output.output_type == "canvas_answer":
        return output.question or ""
    return _TASKS[output.output_type]


def to_run_with_omissions(
    output: ReviewOutput, *, limits: EvidenceLimits | None = None
) -> tuple[Trajectory, list[Omission]]:
    """Build the run for a review output and list which files had content left out and why."""
    scope = scope_evidence(output)
    steps: list[Step] = []
    if scope.changed_files is not None:
        listing = "\n".join(scope.changed_files) or _NO_CHANGED_FILES
        steps.append(Step(tool_call=ToolCall(name=LIST_CHANGED_FILES, output=listing)))
    omissions: list[Omission] = []
    for item in render_diffs(scope.diffs, limits):
        steps.append(Step(tool_call=ToolCall(
            name=READ_DIFF, arguments={"path": item.path}, output=item.text)))
        if item.omission is not None:
            omissions.append(item.omission)
    for read in scope.reads:
        steps.append(Step(tool_call=ToolCall(
            name=read.tool, arguments=dict(read.arguments), output=read.output)))
    omissions.extend(Omission(path, "out_of_scope") for path in scope.dropped_diffs)
    omissions.extend(Omission(read_label(read), "out_of_scope") for read in scope.dropped_reads)
    run = Trajectory(
        task=task_text(output),
        allowed_tools=list(EVIDENCE_TOOLS),
        steps=steps,
        final_answer=output.text,
    )
    return run, omissions


def to_run(output: ReviewOutput, *, limits: EvidenceLimits | None = None) -> Trajectory:
    """Build the run for a review output; evidence comes only from tool calls."""
    return to_run_with_omissions(output, limits=limits)[0]
