from __future__ import annotations

from ..results import CheckResult, Finding, Severity
from ..trajectory import Trajectory
from .deterministic import evaluate_deterministic_rule
from .models import EvaluationPolicy, EvaluationRule
from .semantic import evaluate_semantic_rule


def check_policy(traj: Trajectory, policy: EvaluationPolicy, *, samples: int = 3) -> CheckResult:
    """Evaluate every policy rule against one agent run."""
    findings = [_evaluate_rule(traj, rule, samples=samples) for rule in policy.rules]
    failures = _count(findings, Severity.FAIL)
    warnings = _count(findings, Severity.WARN)
    passed_rules = _count(findings, Severity.PASS)
    return CheckResult(
        check="policy",
        passed=failures == 0,
        score=passed_rules / len(findings) if findings else 1.0,
        summary=(
            f"{passed_rules}/{len(findings)} policy rules passed; "
            f"{failures} failed; {warnings} warned."
        ),
        findings=findings,
        metadata={
            **_policy_identity(policy),
            "semantic_context_truncated": any(_was_truncated(f) for f in findings),
        },
    )


def _evaluate_rule(traj: Trajectory, rule: EvaluationRule, *, samples: int) -> Finding:
    if rule.needs_llm:
        return evaluate_semantic_rule(traj, rule, samples=samples)
    return evaluate_deterministic_rule(traj, rule)


def _count(findings: list[Finding], severity: Severity) -> int:
    return sum(finding.severity is severity for finding in findings)


def _was_truncated(finding: Finding) -> bool:
    metadata: dict[str, object] = finding.metadata
    return bool(metadata.get("semantic_context_truncated", False))


def _policy_identity(policy: EvaluationPolicy) -> dict[str, object]:
    return {"policy": {"name": policy.name, "version": policy.version, "hash": policy.hash}}
