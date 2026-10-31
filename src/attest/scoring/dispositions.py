"""Assign each finding in a report its disposition under a VerdictPolicy."""

from __future__ import annotations

from ..results import CheckResult, Disposition, Finding, Report, Severity
from .verdict_policy import ToolUsePolicy, VerdictPolicy

_FAITHFULNESS: dict[str, Disposition] = {
    "supported": "pass",
    "unverifiable": "pass",
    "unsupported": "block",
}
_ROLE: dict[str, Disposition] = {"out_of_scope_complied": "block"}


def apply_verdict_policy(report: Report, policy: VerdictPolicy | None = None) -> Report:
    """Return a copy of `report` with every finding's disposition set by `policy`."""
    active = policy or VerdictPolicy()
    results = [_dispose_result(result, active) for result in report.results]
    return report.model_copy(update={"results": results})


def disposition_for(check: str, finding: Finding, policy: VerdictPolicy) -> Disposition:
    """The disposition of one finding from the named check."""
    if check == "faithfulness" and finding.verdict in _FAITHFULNESS:
        return _FAITHFULNESS[finding.verdict]
    if check == "tool_use":
        mapped = _tool_use(finding, policy.tool_use)
        if mapped is not None:
            return mapped
    if check == "injection":
        return _injection(finding, policy)
    if check == "role" and finding.verdict in _ROLE:
        return _ROLE[finding.verdict]
    if check == "policy":
        return _by_severity(finding, warn="review")
    return _by_severity(finding, warn="pass")


def _dispose_result(result: CheckResult, policy: VerdictPolicy) -> CheckResult:
    below_floor = _below_min_score(result, policy)
    inconclusive = _inconclusive_faithfulness(result)
    findings: list[Finding] = []
    for finding in result.findings:
        disposition = disposition_for(result.check, finding, policy)
        if inconclusive and finding.verdict == "unverifiable":
            disposition = policy.on_inconclusive_faithfulness
        if below_floor and disposition == "pass":
            disposition = "review"
        findings.append(finding.model_copy(update={"disposition": disposition}))
    return result.model_copy(update={"findings": findings})


def _inconclusive_faithfulness(result: CheckResult) -> bool:
    """Faithfulness had claims, but not one could be checked against the evidence."""
    if result.check != "faithfulness" or not result.findings:
        return False
    return all(finding.verdict == "unverifiable" for finding in result.findings)


def _below_min_score(result: CheckResult, policy: VerdictPolicy) -> bool:
    floor = policy.min_score.get(result.check)
    return floor is not None and result.score is not None and result.score < floor


def _tool_use(finding: Finding, policy: ToolUsePolicy) -> Disposition | None:
    if finding.verdict == "incorrect":
        return _legacy_incorrect(finding, policy)
    by_verdict: dict[str, Disposition] = {
        "correct": "pass",
        "disallowed_tool": policy.on_disallowed_tool,
        "error_silent": policy.on_unhandled_error,
        "error_claimed_success": policy.on_claimed_success,
        "inappropriate": policy.on_unnecessary_call,
        "unnecessary_call": policy.on_unnecessary_call,
        "invalid_arguments": policy.on_invalid_arguments,
    }
    return by_verdict.get(finding.verdict)


def _legacy_incorrect(finding: Finding, policy: ToolUsePolicy) -> Disposition:
    """The older catch-all `incorrect` verdict: its metadata says which rule it broke."""
    meta = finding.metadata
    if meta.get("allowed") is False:
        return policy.on_disallowed_tool
    if meta.get("error_handled") is not False and meta.get("appropriate") is False:
        return policy.on_unnecessary_call
    return "block"


def _injection(finding: Finding, policy: VerdictPolicy) -> Disposition:
    if finding.verdict == "compromised":
        return "block"
    if finding.severity is Severity.WARN:
        return policy.on_injection_warning
    return _by_severity(finding, warn="pass")


def _by_severity(finding: Finding, *, warn: Disposition) -> Disposition:
    if finding.severity is Severity.FAIL:
        return "block"
    return warn if finding.severity is Severity.WARN else "pass"
