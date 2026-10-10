"""Build the Finding recorded for one evaluated rule."""

from __future__ import annotations

from ..core import Finding, Severity
from .rule import EvaluationRule


def _violation_severity(rule: EvaluationRule) -> Severity:
    return Severity.FAIL if rule.severity == "fail" else Severity.WARN


def _finding(
    rule: EvaluationRule,
    compliant: bool,
    reason: str,
    evidence: str | None = None,
    *,
    extra_metadata: dict | None = None,
) -> Finding:
    severity = Severity.PASS if compliant else _violation_severity(rule)
    return Finding(
        severity=severity,
        verdict="compliant" if compliant else "violated",
        subject=rule.id,
        reason=reason,
        evidence=evidence,
        metadata={"rule_id": rule.id, "rule_kind": rule.kind,
                  "configured_severity": rule.severity, **(extra_metadata or {})},
    )
