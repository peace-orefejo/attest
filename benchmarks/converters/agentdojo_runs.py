"""Read vendored AgentDojo runs and map one onto an attest Trajectory."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

ORIGIN = "agentdojo"
PIPELINE = "gpt-4o-2024-05-13"
UPSTREAM_COMMIT = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BENCHMARKS_DIR / "sources" / ORIGIN
DATASETS_DIR = BENCHMARKS_DIR / "datasets"

KEPT_RUN_FIELDS = (
    "suite_name",
    "pipeline_name",
    "user_task_id",
    "injection_task_id",
    "attack_type",
    "injections",
    "messages",
    "error",
)
"""Run fields kept when vendoring. Everything else (`utility`, `security`, `duration`) is
dropped: the first two are AgentDojo's own grading and could act as labels."""


def as_object(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected a JSON object")
    return cast(dict[str, object], value)


def _list(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{where}: expected a JSON list")
    return cast(list[object], value)


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def read_json_object(path: Path) -> dict[str, object]:
    return as_object(json.loads(path.read_text(encoding="utf-8")), str(path))


def strip_run(run: dict[str, object]) -> dict[str, object]:
    """Keep only the run fields the converter needs; drop AgentDojo's grading."""
    return {key: run[key] for key in KEPT_RUN_FIELDS if key in run}


def suite_tools(suite: str, root: Path = SOURCE_DIR) -> list[str]:
    """The suite's tool names, in order, from the `TOOLS = [...]` list in its task_suite.py."""
    path = root / "suites" / suite / "task_suite.py.txt"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in node.targets)
            and isinstance(node.value, ast.List)
        ):
            names = [elt.id for elt in node.value.elts if isinstance(elt, ast.Name)]
            if len(names) != len(node.value.elts):
                raise ValueError(f"{path}: TOOLS holds something other than plain names")
            return names
    raise ValueError(f"{path}: no TOOLS list found")


def _tool_call(call: dict[str, object], result: dict[str, object]) -> dict[str, object]:
    error = result.get("error")
    tool_call: dict[str, object] = {
        "name": _text(call.get("function")),
        "arguments": as_object(call.get("args") or {}, "args"),
        "output": _text(error) if error else _text(result.get("content")),
    }
    if error:
        tool_call["is_error"] = True
    return tool_call


def _steps(messages: list[dict[str, object]]) -> tuple[list[dict[str, object]], str]:
    outputs = {_text(m.get("tool_call_id")): m for m in messages if m.get("role") == "tool"}
    steps: list[dict[str, object]] = []
    final_answer = ""
    for message in messages:
        if message.get("role") != "assistant":
            continue
        thought = _text(message.get("content")).strip()
        raw_calls = message.get("tool_calls")
        calls = [] if raw_calls is None else _list(raw_calls, "tool_calls")
        if not calls:
            final_answer = _text(message.get("content"))
            continue
        for index, raw_call in enumerate(calls):
            call = as_object(raw_call, "tool_calls[]")
            call_id = _text(call.get("id"))
            if call_id not in outputs:
                raise ValueError(f"tool call {call_id!r} has no recorded output")
            step: dict[str, object] = {}
            if thought and index == 0:
                step["thought"] = thought
            step["tool_call"] = _tool_call(call, outputs[call_id])
            steps.append(step)
    return steps, final_answer


def trajectory(run: dict[str, object], tools: list[str]) -> dict[str, object]:
    """Map one AgentDojo run onto an attest Trajectory, as a JSON-ready dict."""
    messages = [as_object(m, "messages[]") for m in _list(run["messages"], "messages")]
    systems = [m for m in messages if m.get("role") == "system"]
    users = [m for m in messages if m.get("role") == "user"]
    if len(users) != 1:
        raise ValueError(f"expected exactly one user message, found {len(users)}")
    steps, final_answer = _steps(messages)
    return {
        "task": _text(users[0].get("content")),
        "system_prompt": _text(systems[0].get("content")) if systems else None,
        "allowed_tools": tools,
        "steps": steps,
        "final_answer": final_answer,
    }
