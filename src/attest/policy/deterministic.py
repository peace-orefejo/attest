from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from ..results import Finding
from ..trajectory import Trajectory
from .findings import rule_finding
from .models import EvaluationRule


class RuleOutcome(BaseModel):
    compliant: bool
    detail: str


def evaluate_deterministic_rule(traj: Trajectory, rule: EvaluationRule) -> Finding:
    evaluator = _EVALUATORS.get(rule.kind)
    if evaluator is None:
        raise ValueError(f"Unsupported deterministic policy rule: {rule.kind}")
    outcome = evaluator(traj, rule)
    reason = "Rule satisfied." if outcome.compliant else outcome.detail
    return rule_finding(rule, outcome.compliant, reason)


def _required_text(traj: Trajectory, rule: EvaluationRule) -> RuleOutcome:
    answer = _fold(traj.final_answer, rule)
    missing = [raw for raw, value in _values(rule) if value not in answer]
    return _outcome(missing, "Missing required text")


def _forbidden_text(traj: Trajectory, rule: EvaluationRule) -> RuleOutcome:
    answer = _fold(traj.final_answer, rule)
    present = [raw for raw, value in _values(rule) if value in answer]
    return _outcome(present, "Forbidden text present")


def _required_tools(traj: Trajectory, rule: EvaluationRule) -> RuleOutcome:
    called = _called_tools(traj, rule)
    missing = [raw for raw, value in _values(rule) if value not in called]
    return _outcome(missing, "Required tools not called")


def _required_tool_order(traj: Trajectory, rule: EvaluationRule) -> RuleOutcome:
    remaining = iter(_called_tools(traj, rule))
    in_order = all(value in remaining for _, value in _values(rule))
    return RuleOutcome(
        compliant=in_order,
        detail=f"Required tool order not observed: {' -> '.join(rule.values)}",
    )


def _allowed_tools(traj: Trajectory, rule: EvaluationRule) -> RuleOutcome:
    allowed = {value for _, value in _values(rule)}
    unexpected = [name for name in _called_tools(traj, rule) if name not in allowed]
    return _outcome(unexpected, "Unallowed tools called")


def _fold(text: str, rule: EvaluationRule) -> str:
    return text if rule.case_sensitive else text.casefold()


def _values(rule: EvaluationRule) -> list[tuple[str, str]]:
    return [(raw, _fold(raw, rule)) for raw in rule.values]


def _called_tools(traj: Trajectory, rule: EvaluationRule) -> list[str]:
    return [_fold(tool.name, rule) for _, tool in traj.tool_calls()]


def _outcome(offending: list[str], label: str) -> RuleOutcome:
    return RuleOutcome(compliant=not offending, detail=f"{label}: {', '.join(offending)}")


_EVALUATORS: dict[str, Callable[[Trajectory, EvaluationRule], RuleOutcome]] = {
    "required_text": _required_text,
    "forbidden_text": _forbidden_text,
    "required_tools": _required_tools,
    "required_tool_order": _required_tool_order,
    "allowed_tools": _allowed_tools,
}
