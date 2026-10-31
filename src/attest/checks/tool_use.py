"""Tool-use correctness: allowed tools, error recovery, optional LLM appropriateness."""

from __future__ import annotations

from pydantic import BaseModel

from ..llm import BudgetExceeded, call, has_active_client
from ..prompts.tool_use import APPROPRIATE_SYSTEM, appropriate_prefix, appropriate_user
from ..results import CheckResult, Finding, Severity
from ..trajectory import ToolCall, Trajectory
from ..utils.failures import failure_reason
from .tool_recovery import RecoveryReview, review_recovery

_RECOVERED = ("retried", "fallback", "acknowledged")
UNCHECKED = "unchecked"
_SEVERITY = {"correct": Severity.PASS, UNCHECKED: Severity.WARN}


class _AppropriatenessOut(BaseModel):
    """Whether the tool call was a reasonable choice for the step."""

    appropriate: bool
    reason: str = ""


class ToolCallReview(BaseModel):
    allowed: bool
    recovery: RecoveryReview | None
    appropriate: bool | None
    appropriate_reason: str = ""
    appropriate_failed: bool = False


def check_tool_use(
    traj: Trajectory, *, appropriate: bool = False, check_answer: bool | None = None
) -> CheckResult:
    """Review each tool call. `appropriate=True` adds the LLM tool-choice check.

    A tool error that no retry or declared fallback recovered is checked against the final
    answer with one model call. `check_answer` turns that on or off; by default it runs when
    `appropriate=True` or a client is scoped with `attest.llm.using`, and the error is reported
    as `unchecked` otherwise.

    `allowed_tools=None` allows every tool; an empty list allows none. If the tool-choice call
    fails (anything but `BudgetExceeded`), that call is `unchecked`, never `correct`.
    """
    if check_answer is None:
        check_answer = appropriate or has_active_client()
    allowed_tools = traj.allowed_tools
    calls = traj.tool_calls()
    shared = len(calls) > 1
    findings: list[Finding] = []
    for step, tool_call in calls:
        review = ToolCallReview(
            allowed=allowed_tools is None or tool_call.name in allowed_tools,
            recovery=review_recovery(traj, step, tool_call, check_answer=check_answer),
            appropriate=None,
        )
        if appropriate:
            _judge_appropriate(review, traj, tool_call, shared=shared)
        findings.append(_finding(step, tool_call, review, set(allowed_tools or [])))
    correct = sum(finding.verdict == "correct" for finding in findings)
    return CheckResult(
        check="tool_use",
        passed=all(finding.severity is not Severity.FAIL for finding in findings),
        score=correct / len(findings) if findings else 1.0,
        summary=_summarize(findings),
        findings=findings,
    )


def _finding(
    step: int, tool_call: ToolCall, review: ToolCallReview, allowed_tools: set[str]
) -> Finding:
    recovery = review.recovery
    error_text = tool_call.output.strip()[:160] or None

    def finding(verdict: str, reason: str, evidence: str | None = None) -> Finding:
        return Finding(
            severity=_SEVERITY.get(verdict, Severity.FAIL),
            verdict=verdict,
            subject=tool_call.name,
            step=step,
            reason=reason,
            evidence=evidence,
            metadata={
                "allowed": review.allowed,
                "recovery": recovery.recovery if recovery else None,
                "recovered_at": recovery.recovered_at if recovery else None,
                "appropriate": review.appropriate,
            },
        )

    if not review.allowed:
        return finding(
            "disallowed_tool",
            f"'{tool_call.name}' is not in the agent's allowed tools {sorted(allowed_tools)}.",
        )
    if recovery is not None and recovery.recovery == "claimed_success":
        return finding("error_claimed_success", _error_reason(recovery), error_text)
    if recovery is not None and recovery.recovery not in _RECOVERED:
        return finding("error_silent", _error_reason(recovery), error_text)
    if review.appropriate is False:
        return finding(
            "incorrect",
            review.appropriate_reason or "Not an appropriate tool choice for this step.",
        )
    if review.appropriate_failed:
        return finding(UNCHECKED, review.appropriate_reason)
    reason = review.appropriate_reason or (
        _error_reason(recovery) if recovery else "Allowed tool; no error."
    )
    return finding("correct", reason)


def _judge_appropriate(
    review: ToolCallReview, traj: Trajectory, tool_call: ToolCall, *, shared: bool
) -> None:
    try:
        judged = _check_appropriate(traj, tool_call, shared=shared)
    except BudgetExceeded:
        raise
    except Exception as error:
        review.appropriate_failed = True
        review.appropriate_reason = failure_reason("The tool-choice check", error)
        return
    review.appropriate, review.appropriate_reason = judged.appropriate, judged.reason


def _check_appropriate(
    traj: Trajectory, tool_call: ToolCall, *, shared: bool = False
) -> _AppropriatenessOut:
    return call(
        system=APPROPRIATE_SYSTEM,
        prefix=appropriate_prefix(traj),
        user=appropriate_user(tool_call),
        output=_AppropriatenessOut,
        reuse="prefix" if shared else None,
    )


def _error_reason(recovery: RecoveryReview) -> str:
    unrecovered = "The tool returned an error that no retry or declared fallback recovered"
    reasons = {
        "retried": f"The tool returned an error; a retry at step {recovery.recovered_at} worked.",
        "fallback": (
            f"The tool returned an error; the fallback at step {recovery.recovered_at} worked."
        ),
        "acknowledged": f"{unrecovered}, and the final answer says it failed.",
        "silent": f"{unrecovered}, and the final answer doesn't mention it.",
        "claimed_success": f"{unrecovered}, but the final answer says it succeeded.",
        "unchecked": (
            f"{unrecovered}. No model was available to check whether the final answer "
            "reports the failure."
        ),
    }
    return reasons[recovery.recovery]


def _summarize(findings: list[Finding]) -> str:
    if not findings:
        return "No tool calls were made."
    correct = sum(finding.verdict == "correct" for finding in findings)
    sequence = " -> ".join(finding.subject for finding in findings)
    parts = [f"{correct}/{len(findings)} tool calls correct.", f"Sequence: {sequence}."]
    issues = [finding for finding in findings if finding.verdict != "correct"]
    if not issues:
        parts.append("All tools allowed; no unrecovered errors.")
        return " ".join(parts)
    details = "; ".join(f"step {f.step} ({f.subject}) — {f.reason}" for f in issues)
    parts.append(f"Issues: {details}")
    unchecked = sum(f.metadata.get("recovery") == "unchecked" for f in findings)
    if unchecked:
        parts.append(f"{unchecked} error(s) unchecked: no model read the final answer.")
    return " ".join(parts)
