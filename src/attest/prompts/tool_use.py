from __future__ import annotations

from ..trajectory import ToolCall, Trajectory

APPROPRIATE_SYSTEM = (
    "You judge whether an AI agent chose an APPROPRIATE TOOL for a step — not "
    "whether the final answer is good. Given the task, the tools available to the "
    "agent (with descriptions), and the specific call it made, decide whether "
    "calling that tool with those arguments was a reasonable step toward the task. "
    "Judge tool CHOICE only."
)


def appropriate_prefix(traj: Trajectory) -> str:
    return (
        f"TASK:\n{traj.task}\n\n"
        f"TOOLS AVAILABLE (from the agent's system prompt):\n"
        f"{traj.system_prompt or '(no tool descriptions provided)'}"
    )


def appropriate_user(call: ToolCall) -> str:
    return f"TOOL CALL:\n{call.name}({call.arguments})"
