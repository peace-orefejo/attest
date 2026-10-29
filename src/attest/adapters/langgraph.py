"""Turn a LangGraph/LangChain message list into an attest Trajectory. Duck-typed."""

from __future__ import annotations

from collections.abc import Sequence

from ..trajectory import Step, ToolCall, Trajectory
from .guards import is_object_dict, is_object_list, str_attr

_CLASS_ROLES = {
    "SystemMessage": "system",
    "HumanMessage": "human",
    "AIMessage": "ai",
    "AIMessageChunk": "ai",
    "ToolMessage": "tool",
    "FunctionMessage": "tool",
}


def from_langgraph_messages(
    messages: Sequence[object],
    *,
    task: str | None = None,
    final_answer: str | None = None,
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    response_tool: str | None = None,
) -> Trajectory:
    """
    Convert a LangGraph/LangChain message list into a Trajectory.

    `task` defaults to the first HumanMessage; `final_answer` to the last AIMessage's
    text (pass it for structured responses); `system_prompt` to a SystemMessage if
    present. `response_tool` names a structured-output synthetic tool to skip.
    """
    outputs = _tool_outputs(messages)

    steps: list[Step] = []
    first_human: str | None = None
    detected_system: str | None = None
    last_ai_text = ""
    for m in messages:
        role = _role(m)
        content = _content(m)
        if role == "system" and detected_system is None:
            detected_system = content
        if role == "human" and first_human is None:
            first_human = content
        tool_calls = _tool_call_dicts(m)
        for tc in tool_calls:
            if response_tool and tc.get("name") == response_tool:
                continue
            steps.append(Step(thought=content or None, tool_call=_tool_call(tc, outputs)))
        if role == "ai" and not tool_calls and content:
            last_ai_text = content

    return Trajectory(
        task=task or first_human or "",
        system_prompt=system_prompt if system_prompt is not None else detected_system,
        allowed_tools=allowed_tools,
        steps=steps,
        final_answer=final_answer if final_answer is not None else last_ai_text,
    )


def _tool_outputs(messages: Sequence[object]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for m in messages:
        tool_call_id = str_attr(m, "tool_call_id")
        if tool_call_id is not None:
            outputs[tool_call_id] = _content(m)
    return outputs


def _tool_call(tc: dict[str, object], outputs: dict[str, str]) -> ToolCall:
    name = tc.get("name", "tool")
    args = tc.get("args")
    call_id = tc.get("id", "")
    return ToolCall(
        name=name if isinstance(name, str) else "tool",
        arguments=args if is_object_dict(args) else {},
        output=outputs.get(call_id, "") if isinstance(call_id, str) else "",
    )


def _tool_call_dicts(m: object) -> list[dict[str, object]]:
    tool_calls: object = getattr(m, "tool_calls", None)
    if not is_object_list(tool_calls):
        return []
    return [tc for tc in tool_calls if is_object_dict(tc)]


def _content(m: object) -> str:
    return _flatten(getattr(m, "content", ""))


def _flatten(content: object) -> str:
    if isinstance(content, str):
        return content
    if is_object_list(content):
        parts = [_block_text(block) for block in content]
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


def _block_text(block: object) -> str:
    if not is_object_dict(block):
        return str(block)
    text = block.get("text", "")
    return text if isinstance(text, str) else str(text)


def _role(m: object) -> str:
    """LangChain's stable message role (``BaseMessage.type``), class name as a fallback."""
    role = str_attr(m, "type")
    if role:
        return role
    name = type(m).__name__
    if name == "ChatMessage":
        return str_attr(m, "role") or "chat"
    return _CLASS_ROLES.get(name, name)
