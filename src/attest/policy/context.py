"""Bounded, escaped agent-run context for the semantic policy judge."""

from __future__ import annotations

import html
import json

from ..core import Trajectory
from .limits import (
    POLICY_MAX_ANSWER_CHARS,
    POLICY_MAX_ARGUMENT_CHARS,
    POLICY_MAX_EVIDENCE_CHARS,
    POLICY_MAX_OUTPUT_CHARS,
    POLICY_MAX_TASK_CHARS,
    POLICY_MAX_TOOL_CALLS,
)


def _bounded_policy_context(traj: Trajectory) -> tuple[str, bool]:
    """Return escaped structured agent data with hard per-field and total evidence limits."""
    truncated = False

    def clip(value: str, limit: int) -> str:
        nonlocal truncated
        if len(value) > limit:
            truncated = True
            return value[:limit]
        return value

    tools = []
    evidence_used = 0
    calls = traj.tool_calls()
    if len(calls) > POLICY_MAX_TOOL_CALLS:
        truncated = True
    for index, tool in calls[:POLICY_MAX_TOOL_CALLS]:
        arguments = clip(
            json.dumps(tool.arguments, ensure_ascii=False, default=str),
            POLICY_MAX_ARGUMENT_CHARS,
        )
        remaining = max(0, POLICY_MAX_EVIDENCE_CHARS - evidence_used)
        output_limit = min(POLICY_MAX_OUTPUT_CHARS, remaining)
        output = clip(tool.output, output_limit) if output_limit else ""
        if output_limit == 0 and tool.output:
            truncated = True
        evidence_used += len(output)
        tools.append({"step": index, "name": tool.name,
                      "arguments": arguments, "output": output})

    payload = {
        "task": clip(traj.task, POLICY_MAX_TASK_CHARS),
        "tool_calls": tools,
        "final_answer": clip(traj.final_answer, POLICY_MAX_ANSWER_CHARS),
        "truncated": truncated,
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    # Escaping prevents attacker text from closing the structural wrapper. JSON encoding keeps
    # forged field labels inside string values rather than creating new prompt sections.
    return html.escape(serialized, quote=False), truncated
