"""Assign each finding in a report its disposition under a VerdictPolicy."""

from __future__ import annotations

from ..disposition_rules import disposition_for as rule_for
from ..disposition_rules import result_dispositions
from ..results import CheckResult, Disposition, Finding, Report, claim_coverage
from .verdict_policy import VerdictPolicy


def apply_verdict_policy(report: Report, policy: VerdictPolicy | None = None) -> Report:
    """Return a copy of `report` with every finding's disposition set by `policy`."""
    active = policy or VerdictPolicy()
    results = [_dispose_result(result, active) for result in report.results]
    return report.model_copy(update={"results": results})


def disposition_for(check: str, finding: Finding, policy: VerdictPolicy) -> Disposition:
    """The disposition of one finding from the named check."""
    return rule_for(check, finding, policy)


def _dispose_result(result: CheckResult, policy: VerdictPolicy) -> CheckResult:
    below_floor = _below_min_score(result, policy) or _below_min_coverage(result, policy)
    dispositions = result_dispositions(result.check, result.findings, policy)
    findings: list[Finding] = []
    for finding, disposition in zip(result.findings, dispositions, strict=True):
        if below_floor and disposition == "pass":
            disposition = "review"
        findings.append(finding.model_copy(update={"disposition": disposition}))
    return result.model_copy(update={"findings": findings})


def _below_min_coverage(result: CheckResult, policy: VerdictPolicy) -> bool:
    floor = policy.min_claim_coverage
    if floor is None or result.check != "faithfulness":
        return False
    coverage = claim_coverage(result)
    return coverage is not None and coverage < floor


def _below_min_score(result: CheckResult, policy: VerdictPolicy) -> bool:
    floor = policy.min_score.get(result.check)
    return floor is not None and result.score is not None and result.score < floor
