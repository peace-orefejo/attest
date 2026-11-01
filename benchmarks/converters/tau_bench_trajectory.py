"""Turn one upstream run into an attest trajectory: task, policy, tool calls and answer."""

from __future__ import annotations

import json

# isort: split
from tau_bench_spec import CaseSpec
from tau_bench_upstream import TOOLS, Domain, Message, Run

STOP_TOKEN = "###STOP###"


def user_text(message: Message) -> str:
    return (message.content or "").replace(STOP_TOKEN, "").strip()


def task_text(traj: list[Message], later_turns: tuple[int, ...]) -> str:
    users = [index for index, message in enumerate(traj) if message.role == "user"]
    for index in later_turns:
        if index not in users[1:]:
            raise ValueError(f"turn {index} is not a later user turn")
    parts = [user_text(traj[users[0]])]
    parts.extend(f"Later the user said: {user_text(traj[index])}" for index in later_turns)
    return "\n\n".join(parts)


def tool_output(traj: list[Message], after: int, call_id: str) -> str:
    """The first tool message answering `call_id` after the call. Upstream reuses some call
    ids within a run, so outputs are matched by position as well as id."""
    for message in traj[after + 1 :]:
        if message.role == "tool" and message.tool_call_id == call_id:
            return message.content or ""
    raise ValueError(f"tool call {call_id} has no recorded output")


def steps(traj: list[Message]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for index, message in enumerate(traj):
        for position, call in enumerate(message.tool_calls or []):
            step: dict[str, object] = {}
            if position == 0 and message.content:
                step["thought"] = message.content
            arguments: dict[str, object] = json.loads(call.function.arguments)
            step["tool_call"] = {
                "name": call.function.name,
                "arguments": arguments,
                "output": tool_output(traj, index, call.id),
            }
            result.append(step)
    return result


def final_answer(traj: list[Message]) -> str:
    texts = [m.content for m in traj if m.role == "assistant" and m.content and not m.tool_calls]
    if not texts:
        raise ValueError("run has no assistant message to the user")
    return texts[-1]


def trajectory(run: Run, spec: CaseSpec, domain: Domain) -> dict[str, object]:
    system = [m.content for m in run.traj if m.role == "system" and m.content]
    return {
        "task": task_text(run.traj, spec.later_user_turns),
        "system_prompt": system[0],
        "allowed_tools": TOOLS[domain],
        "steps": steps(run.traj),
        "final_answer": final_answer(run.traj),
    }
