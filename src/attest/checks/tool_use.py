"""Tool-use correctness: allowed-tool + error-handling checks, optional LLM appropriateness."""

from __future__ import annotations

from pydantic import BaseModel

from ..llm import call
from ..prompts.tool_use import APPROPRIATE_SYSTEM, appropriate_prefix, appropriate_user
from ..results import CheckResult, Finding, Severity
from ..trajectory import ToolCall, Trajectory

_ERROR_PREFIXES = ("error", "exception", "traceback")
_ERROR_MARKERS = ("traceback (most recent call last)", "error:", "exception:")


class _AppropriatenessOut(BaseModel):
    """Whether the tool call was a reasonable choice for the step."""

    appropriate: bool
    reason: str = ""


class ToolCallReview(BaseModel):
    allowed: bool
    error_handled: bool | None
    appropriate: bool | None
    appropriate_reason: str = ""


def check_tool_use(traj: Trajectory, *, appropriate: bool = False) -> CheckResult:
    """Review each tool call. `appropriate=True` adds the LLM tool-choice check."""
    allowed_tools = set(traj.allowed_tools or [])
    calls = traj.tool_calls()
    shared = len(calls) > 1
    findings = [
        _review_finding(
            traj, step, tool_call, allowed_tools, appropriate=appropriate, shared=shared
        )
        for step, tool_call in calls
    ]
    correct = sum(finding.verdict == "correct" for finding in findings)
    return CheckResult(
        check="tool_use",
        passed=all(finding.severity is not Severity.FAIL for finding in findings),
        score=correct / len(findings) if findings else 1.0,
        summary=_summarize(findings),
        findings=findings,
    )


def _review_finding(
    traj: Trajectory,
    step: int,
    tool_call: ToolCall,
    allowed_tools: set[str],
    *,
    appropriate: bool,
    shared: bool,
) -> Finding:
    review = _review(traj, step, tool_call, allowed_tools, appropriate=appropriate, shared=shared)
    is_error = review.error_handled is not None

    def finding(
        verdict: str, severity: Severity, reason: str, evidence: str | None = None
    ) -> Finding:
        return Finding(
            severity=severity,
            verdict=verdict,
            subject=tool_call.name,
            step=step,
            reason=reason,
            evidence=evidence,
            metadata={
                "allowed": review.allowed,
                "error_handled": review.error_handled,
                "appropriate": review.appropriate,
            },
        )

    if not review.allowed:
        return finding(
            "incorrect",
            Severity.FAIL,
            f"'{tool_call.name}' is not in the agent's allowed tools {sorted(allowed_tools)}.",
        )
    if is_error and not review.error_handled:
        return finding(
            "incorrect",
            Severity.FAIL,
            "The tool returned an error that no later step addressed.",
            tool_call.output.strip()[:160] or None,
        )
    if review.appropriate is False:
        return finding(
            "incorrect",
            Severity.FAIL,
            review.appropriate_reason or "Not an appropriate tool choice for this step.",
        )
    return finding(
        "correct", Severity.PASS, review.appropriate_reason or "Allowed tool; no unhandled error."
    )


def _review(
    traj: Trajectory,
    step: int,
    tool_call: ToolCall,
    allowed_tools: set[str],
    *,
    appropriate: bool,
    shared: bool,
) -> ToolCallReview:
    is_error = _looks_like_error(tool_call.output)
    judged = _check_appropriate(traj, tool_call, shared=shared) if appropriate else None
    return ToolCallReview(
        allowed=not allowed_tools or tool_call.name in allowed_tools,
        error_handled=_handled_later(traj, step) if is_error else None,
        appropriate=judged.appropriate if judged else None,
        appropriate_reason=judged.reason if judged else "",
    )


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


def _looks_like_error(output: str) -> bool:
    text = output.strip().lower()
    if not text:
        return True
    return text.startswith(_ERROR_PREFIXES) or any(marker in text for marker in _ERROR_MARKERS)


def _handled_later(traj: Trajectory, error_step: int) -> bool:
    return any(step > error_step for step, _ in traj.tool_calls())


def _summarize(findings: list[Finding]) -> str:
    if not findings:
        return "No tool calls were made."
    correct = sum(finding.verdict == "correct" for finding in findings)
    sequence = " -> ".join(finding.subject for finding in findings)
    parts = [f"{correct}/{len(findings)} tool calls correct.", f"Sequence: {sequence}."]
    issues = [finding for finding in findings if finding.verdict != "correct"]
    if not issues:
        parts.append("All tools allowed; no unhandled errors.")
        return " ".join(parts)
    details = "; ".join(f"step {f.step} ({f.subject}) — {f.reason}" for f in issues)
    parts.append(f"Issues: {details}")
    return " ".join(parts)
