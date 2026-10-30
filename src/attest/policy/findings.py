from __future__ import annotations

from ..results import Finding, Severity
from .models import EvaluationRule


def violation_severity(rule: EvaluationRule) -> Severity:
    return Severity.FAIL if rule.severity == "fail" else Severity.WARN


def rule_metadata(rule: EvaluationRule) -> dict[str, object]:
    return {
        "rule_id": rule.id,
        "rule_kind": rule.kind,
        "configured_severity": rule.severity,
    }


def rule_finding(
    rule: EvaluationRule,
    compliant: bool,
    reason: str,
    evidence: str | None = None,
    *,
    extra_metadata: dict[str, object] | None = None,
) -> Finding:
    return Finding(
        severity=Severity.PASS if compliant else violation_severity(rule),
        verdict="compliant" if compliant else "violated",
        subject=rule.id,
        reason=reason,
        evidence=evidence,
        metadata={**rule_metadata(rule), **(extra_metadata or {})},
    )
