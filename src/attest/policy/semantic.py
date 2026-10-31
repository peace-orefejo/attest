from __future__ import annotations

import json

from pydantic import BaseModel

from ..llm import BudgetExceeded, ProviderConfigError, vote
from ..prompts.policy import POLICY_SYSTEM, policy_user
from ..results import Finding, Severity
from ..trajectory import Trajectory
from ..utils.failures import failure_reason
from .context import bounded_policy_context
from .findings import rule_finding, rule_metadata, violation_severity
from .models import EvaluationRule

_TRUNCATED_REASON = (
    "The agent run exceeded the bounded semantic-policy context, so this rule "
    "could not be certified as compliant."
)


class PolicyVerdict(BaseModel):
    compliant: bool
    reason: str = ""
    evidence_quote: str | None = None


def evaluate_semantic_rule(traj: Trajectory, rule: EvaluationRule, *, samples: int) -> Finding:
    """Judge one rubric or evidence rule. A failed judge call is an `unchecked` warning."""
    context = bounded_policy_context(traj)
    try:
        verdict = _judge(rule, context.text, samples=samples)
    except (BudgetExceeded, ProviderConfigError):
        raise
    except Exception as error:
        return _unchecked_finding(rule, failure_reason("The policy judge", error))
    if context.truncated:
        return _incomplete_finding(rule, verdict)
    return rule_finding(
        rule,
        verdict.compliant,
        verdict.reason,
        verdict.evidence_quote,
        extra_metadata={"semantic_context_truncated": False},
    )


def _judge(rule: EvaluationRule, context: str, *, samples: int) -> PolicyVerdict:
    return vote(
        system=POLICY_SYSTEM,
        user=policy_user(_rule_json(rule), context),
        output=PolicyVerdict,
        key=lambda result: result.compliant,
        samples=samples,
    )


def _rule_json(rule: EvaluationRule) -> str:
    return json.dumps(
        {"id": rule.id, "kind": rule.kind, "description": rule.description},
        ensure_ascii=False,
    )


def _unchecked_finding(rule: EvaluationRule, reason: str) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unchecked",
        subject=rule.id,
        reason=reason,
        metadata={**rule_metadata(rule), "semantic_context_truncated": False},
    )


def _incomplete_finding(rule: EvaluationRule, verdict: PolicyVerdict) -> Finding:
    return Finding(
        severity=violation_severity(rule),
        verdict="incomplete",
        subject=rule.id,
        reason=_TRUNCATED_REASON,
        evidence=verdict.evidence_quote,
        metadata={
            **rule_metadata(rule),
            "semantic_context_truncated": True,
            "partial_judge_reason": verdict.reason,
        },
    )
