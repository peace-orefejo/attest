"""Run every rule of a policy against a trajectory and roll up the CheckResult."""

from __future__ import annotations

from ..core import CheckResult, Finding, Severity, Trajectory
from .deterministic import _evaluate_deterministic_rule
from .models import EvaluationPolicy
from .rule import EvaluationRule
from .semantic import _evaluate_semantic_rule


def check_policy(
    traj: Trajectory, policy: EvaluationPolicy, *, samples: int = 3
) -> CheckResult:
    findings = [_evaluate_rule(traj, rule, samples=samples) for rule in policy.rules]
    failures = sum(f.severity is Severity.FAIL for f in findings)
    warnings = sum(f.severity is Severity.WARN for f in findings)
    passed_rules = sum(f.severity is Severity.PASS for f in findings)
    context_truncated = any(
        finding.metadata.get("semantic_context_truncated", False) for finding in findings
    )
    return CheckResult(
        check="policy",
        passed=failures == 0,
        score=passed_rules / len(findings) if findings else 1.0,
        summary=(f"{passed_rules}/{len(findings)} policy rules passed; "
                 f"{failures} failed; {warnings} warned."),
        findings=findings,
        metadata={**_policy_identity(policy),
                  "semantic_context_truncated": context_truncated},
    )


def _evaluate_rule(traj: Trajectory, rule: EvaluationRule, *, samples: int) -> Finding:
    if rule.needs_llm:
        return _evaluate_semantic_rule(traj, rule, samples=samples)
    return _evaluate_deterministic_rule(traj, rule)


def _policy_identity(policy: EvaluationPolicy) -> dict:
    return {"policy": {"name": policy.name, "version": policy.version, "hash": policy.hash}}
