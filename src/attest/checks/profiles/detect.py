from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from ...trajectory import ToolCall, Trajectory
from .signals import CODE_TOOLS, code_line_count, has_diff, source_file_in

DetectedKind = Literal["code", "factual"]

MIN_CODE_LINES = 3


class KindDetection(BaseModel):
    """The answer kind picked from a run's tool evidence and why."""

    kind: DetectedKind
    reason: str


def detect_answer_kind(traj: Trajectory) -> KindDetection:
    """Pick "code" or "factual" from the run's tool calls. Makes no model calls."""
    calls = traj.tool_calls()
    if not calls:
        return KindDetection(kind="factual", reason="no tool calls recorded")
    for signal in _SIGNALS:
        for step, call in calls:
            reason = signal(call)
            if reason:
                return KindDetection(
                    kind="code", reason=f"{reason} (step {step}, tool {call.name})"
                )
    return KindDetection(kind="factual", reason=f"no code evidence in {len(calls)} tool call(s)")


def _code_tool(call: ToolCall) -> str | None:
    return f"code review tool {call.name} was called" if call.name in CODE_TOOLS else None


def _diff_output(call: ToolCall) -> str | None:
    return "unified diff in tool output" if has_diff(call.output) else None


def _source_path(call: ToolCall) -> str | None:
    token = source_file_in(call.arguments)
    return f"source file {token!r} in tool arguments" if token else None


def _code_shaped_output(call: ToolCall) -> str | None:
    hits = code_line_count(call.output)
    return f"code-shaped tool output ({hits} code lines)" if hits >= MIN_CODE_LINES else None


_SIGNALS: tuple[Callable[[ToolCall], str | None], ...] = (
    _code_tool,
    _diff_output,
    _source_path,
    _code_shaped_output,
)
