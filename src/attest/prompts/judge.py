from __future__ import annotations

from ..trajectory import Trajectory

JUDGE_SYSTEM = (
    "You are evaluating an AI agent's work. You are shown the agent's full "
    "trajectory — its reasoning, the actions it took, and its final answer. "
    "Decide whether the final answer is correct and well-justified, and set "
    "passed=true if it is a good answer."
)


def judge_user(traj: Trajectory) -> str:
    lines = [f"TASK: {traj.task}", ""]
    for step in traj.steps:
        if step.thought:
            lines.append(f"Thought: {step.thought}")
        if step.tool_call:
            call = step.tool_call
            lines.append(f"Action: {call.name}({call.arguments}) -> {call.output}")
    lines += ["", f"FINAL ANSWER: {traj.final_answer}"]
    return "\n".join(lines)
