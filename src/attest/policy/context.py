from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from ..trajectory import ToolCall, Trajectory
from ..utils.markup import escape_markup
from .limits import (
    POLICY_MAX_ANSWER_CHARS,
    POLICY_MAX_ARGUMENT_CHARS,
    POLICY_MAX_EVIDENCE_CHARS,
    POLICY_MAX_OUTPUT_CHARS,
    POLICY_MAX_TASK_CHARS,
    POLICY_MAX_TOOL_CALLS,
)


class PolicyContext(BaseModel):
    text: str
    truncated: bool


class _Clipped(BaseModel):
    value: str
    truncated: bool


class _ToolEntry(BaseModel):
    step: int
    name: str
    arguments: str
    output: str


class _BoundedTools(BaseModel):
    entries: list[_ToolEntry]
    truncated: bool


def bounded_policy_context(traj: Trajectory) -> PolicyContext:
    """Return escaped structured agent data with hard per-field and total evidence limits."""
    calls = traj.tool_calls()
    task = _clip(traj.task, POLICY_MAX_TASK_CHARS)
    tools = _bounded_tool_calls(calls[:POLICY_MAX_TOOL_CALLS])
    answer = _clip(traj.final_answer, POLICY_MAX_ANSWER_CHARS)
    truncated = (
        len(calls) > POLICY_MAX_TOOL_CALLS or task.truncated or tools.truncated or answer.truncated
    )
    payload = {
        "task": task.value,
        "tool_calls": [entry.model_dump() for entry in tools.entries],
        "final_answer": answer.value,
        "truncated": truncated,
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    # Escaping prevents attacker text from closing the structural wrapper. JSON encoding keeps
    # forged field labels inside string values rather than creating new prompt sections.
    return PolicyContext(text=escape_markup(serialized), truncated=truncated)


def _bounded_tool_calls(calls: Sequence[tuple[int, ToolCall]]) -> _BoundedTools:
    entries: list[_ToolEntry] = []
    truncated = False
    evidence_used = 0
    for index, tool in calls:
        arguments = _clip(_serialize_arguments(tool), POLICY_MAX_ARGUMENT_CHARS)
        output = _clip_output(tool.output, POLICY_MAX_EVIDENCE_CHARS - evidence_used)
        evidence_used += len(output.value)
        truncated = truncated or arguments.truncated or output.truncated
        entries.append(
            _ToolEntry(step=index, name=tool.name, arguments=arguments.value, output=output.value)
        )
    return _BoundedTools(entries=entries, truncated=truncated)


def _serialize_arguments(tool: ToolCall) -> str:
    arguments: dict[str, object] = tool.arguments
    return json.dumps(arguments, ensure_ascii=False, default=str)


def _clip_output(output: str, remaining_budget: int) -> _Clipped:
    limit = min(POLICY_MAX_OUTPUT_CHARS, max(0, remaining_budget))
    if limit == 0:
        return _Clipped(value="", truncated=bool(output))
    return _clip(output, limit)


def _clip(value: str, limit: int) -> _Clipped:
    if len(value) > limit:
        return _Clipped(value=value[:limit], truncated=True)
    return _Clipped(value=value, truncated=False)
