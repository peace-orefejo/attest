"""How an agent recovered from a tool error: a retry, a declared fallback, or its final answer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..llm import call
from ..prompts.tool_errors import ERROR_ANSWER_SYSTEM, error_answer_prefix, error_answer_user
from ..trajectory import ToolCall, Trajectory

Recovery = Literal["retried", "fallback", "acknowledged", "silent", "claimed_success", "unchecked"]

_ERROR_PREFIXES = ("error", "exception", "traceback")
_ERROR_MARKERS = ("traceback (most recent call last)", "error:", "exception:")
_ANSWER_RECOVERY: dict[str, Recovery] = {
    "failed": "acknowledged",
    "succeeded": "claimed_success",
    "not_mentioned": "silent",
}


class _AnswerReport(BaseModel):
    """What the final answer says about one failed tool call."""

    outcome: Literal["failed", "succeeded", "not_mentioned"]
    reason: str = ""


class RecoveryReview(BaseModel):
    recovery: Recovery
    recovered_at: int | None = None
    reason: str = ""


def is_error(tool_call: ToolCall) -> bool:
    """`ToolCall.is_error` when set, otherwise whether the output looks like an error."""
    if tool_call.is_error is not None:
        return tool_call.is_error
    text = tool_call.output.strip().lower()
    if not text:
        return True
    return text.startswith(_ERROR_PREFIXES) or any(marker in text for marker in _ERROR_MARKERS)


def review_recovery(
    traj: Trajectory, step: int, tool_call: ToolCall, *, check_answer: bool
) -> RecoveryReview | None:
    """Classify recovery from an errored call, or None when the call didn't error.

    Only the same tool or a fallback declared in `traj.tool_fallbacks` can recover a call. The
    final answer is read by a model only when nothing recovered it and `check_answer` is set.
    """
    if not is_error(tool_call):
        return None
    recovered = _recovered_by_later_call(traj, step, tool_call.name)
    if recovered is not None:
        return recovered
    if not check_answer:
        return RecoveryReview(recovery="unchecked")
    report = _ask_answer(traj, step, tool_call)
    return RecoveryReview(recovery=_ANSWER_RECOVERY[report.outcome], reason=report.reason)


def _recovered_by_later_call(traj: Trajectory, step: int, name: str) -> RecoveryReview | None:
    fallbacks = set(traj.tool_fallbacks.get(name, []))
    for later_step, later in traj.tool_calls():
        if later_step <= step or is_error(later):
            continue
        if later.name == name:
            return RecoveryReview(recovery="retried", recovered_at=later_step)
        if later.name in fallbacks:
            return RecoveryReview(recovery="fallback", recovered_at=later_step)
    return None


def _ask_answer(traj: Trajectory, step: int, tool_call: ToolCall) -> _AnswerReport:
    return call(
        system=ERROR_ANSWER_SYSTEM,
        prefix=error_answer_prefix(traj.final_answer),
        user=error_answer_user(step, tool_call.name, tool_call.output),
        output=_AnswerReport,
    )
