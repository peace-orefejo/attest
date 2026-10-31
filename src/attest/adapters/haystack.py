"""Turn a Haystack 2.x Agent's message list into an attest Trajectory. Duck-typed."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from ..trajectory import Step, ToolCall, Trajectory
from ..utils.json_types import JsonObject
from .haystack_messages import HaystackCall, HaystackMessage, HaystackResult, read_message


class _PairedCall(BaseModel):
    call: HaystackCall
    thought: str | None
    output: str | None = None


class _Run(BaseModel):
    messages: list[HaystackMessage] = Field(default_factory=list[HaystackMessage])

    def first_text(self, role: str) -> str | None:
        return next((m.text for m in self.messages if m.role == role and m.text), None)

    def final_answer(self) -> str:
        answers = [
            m.text for m in self.messages if m.role == "assistant" and not m.tool_calls and m.text
        ]
        return answers[-1] if answers else ""


def from_haystack_messages(
    messages: Sequence[object],
    *,
    task: str | None = None,
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
) -> Trajectory:
    """
    Convert a Haystack 2.x `Agent` run (`result["messages"]`) into a Trajectory.

    Accepts `ChatMessage` objects or their `to_dict()` form. Each tool call is paired with
    the `ToolCallResult` whose `origin` has the same id, falling back to order. `task`
    defaults to the first user message; `system_prompt` to the first system message. The
    final answer is the text of the last assistant message that makes no tool calls.
    """
    run = _Run(messages=[read_message(m) for m in messages])
    detected_system = run.first_text("system")
    return Trajectory(
        task=task or run.first_text("user") or "",
        system_prompt=system_prompt if system_prompt is not None else detected_system,
        allowed_tools=allowed_tools,
        steps=[_step(p) for p in _paired_calls(run.messages)],
        final_answer=run.final_answer(),
    )


def _paired_calls(messages: list[HaystackMessage]) -> list[_PairedCall]:
    calls = [
        _PairedCall(call=call, thought=m.text)
        for m in messages
        if m.role == "assistant"
        for call in m.tool_calls
    ]
    results = [r for m in messages for r in m.tool_call_results]
    unmatched = [r for r in results if not _match_by_id(r, calls)]
    waiting = [c for c in calls if c.output is None]
    for paired, result in zip(waiting, unmatched, strict=False):
        paired.output = result.result
    return calls


def _match_by_id(result: HaystackResult, calls: list[_PairedCall]) -> bool:
    if result.origin_id is None:
        return False
    for paired in calls:
        if paired.output is None and paired.call.id == result.origin_id:
            paired.output = result.result
            return True
    return False


def _step(paired: _PairedCall) -> Step:
    arguments: JsonObject = paired.call.arguments
    return Step(
        thought=paired.thought,
        tool_call=ToolCall(
            name=paired.call.tool_name, arguments=arguments, output=paired.output or ""
        ),
    )
