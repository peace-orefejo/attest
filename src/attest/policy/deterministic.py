"""Rules decided from the answer text and tool calls alone, without an LLM."""

from __future__ import annotations

from ..core import Finding, Trajectory
from .findings import _finding
from .rule import EvaluationRule


def _evaluate_deterministic_rule(traj: Trajectory, rule: EvaluationRule) -> Finding:
    answer = traj.final_answer if rule.case_sensitive else traj.final_answer.casefold()
    values = rule.values if rule.case_sensitive else [value.casefold() for value in rule.values]
    called = [tool.name for _, tool in traj.tool_calls()]
    if not rule.case_sensitive:
        called = [name.casefold() for name in called]

    if rule.kind == "required_text":
        missing = [raw for raw, value in zip(rule.values, values) if value not in answer]
        compliant, detail = not missing, f"Missing required text: {', '.join(missing)}"
    elif rule.kind == "forbidden_text":
        present = [raw for raw, value in zip(rule.values, values) if value in answer]
        compliant, detail = not present, f"Forbidden text present: {', '.join(present)}"
    elif rule.kind == "required_tools":
        missing = [raw for raw, value in zip(rule.values, values) if value not in called]
        compliant, detail = not missing, f"Required tools not called: {', '.join(missing)}"
    elif rule.kind == "required_tool_order":
        positions = []
        cursor = 0
        for value in values:
            try:
                position = called.index(value, cursor)
            except ValueError:
                positions = []
                break
            positions.append(position)
            cursor = position + 1
        compliant = len(positions) == len(values)
        detail = f"Required tool order not observed: {' -> '.join(rule.values)}"
    elif rule.kind == "allowed_tools":
        allowed = set(values)
        unexpected = [name for name in called if name not in allowed]
        compliant, detail = not unexpected, f"Unallowed tools called: {', '.join(unexpected)}"
    else:  # schema validation makes this unreachable
        raise ValueError(f"Unsupported deterministic policy rule: {rule.kind}")
    return _finding(rule, compliant, "Rule satisfied." if compliant else detail)
