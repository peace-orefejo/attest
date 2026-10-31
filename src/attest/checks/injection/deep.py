from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from ...content import TextSegment
from ...llm import BudgetExceeded, ProviderConfigError, vote
from ...prompts.injection import AUTH_SYSTEM, authorization_user
from ...results import Finding, Severity
from ...trajectory import Trajectory
from ...utils.failures import failure_reason
from .coverage import artifact_locations
from .untrusted_view import bounded_untrusted_view


class _AuthOut(BaseModel):
    """Whether the agent took an action beyond what the principal authorized."""

    unauthorized: bool
    action: str = ""
    step: int = -1
    reason: str = ""


class DeepOutcome(BaseModel):
    findings: list[Finding] = Field(default_factory=list[Finding])
    incomplete_locations: set[str] = Field(default_factory=set[str])
    context_truncated: bool = False


def run_deep_check(traj: Trajectory, segments: Sequence[TextSegment], samples: int) -> DeepOutcome:
    """Ask whether the agent acted beyond its authorization; a failed judge call is `unchecked`."""
    view = bounded_untrusted_view(segments)
    outcome = DeepOutcome(context_truncated=view.truncated)
    if view.truncated:
        outcome.incomplete_locations = artifact_locations(segments)
        outcome.findings.append(_truncated_context_finding(len(outcome.incomplete_locations)))
    try:
        auth = check_authorization(traj, view.text, samples=samples)
    except (BudgetExceeded, ProviderConfigError):
        raise
    except Exception as error:
        outcome.findings.append(_unchecked_finding(failure_reason("The deep check", error)))
        return outcome
    if auth.unauthorized:
        outcome.findings.append(_compromised_finding(auth))
    return outcome


def check_authorization(traj: Trajectory, untrusted_view: str, samples: int = 3) -> _AuthOut:
    return vote(
        system=AUTH_SYSTEM,
        user=authorization_user(traj, untrusted_view),
        output=_AuthOut,
        key=lambda out: out.unauthorized,
        samples=samples,
    )


def _unchecked_finding(reason: str) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unchecked",
        subject="deep-analysis",
        reason=reason,
        metadata={"deep_checked": False},
    )


def _truncated_context_finding(artifacts_affected: int) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject="deep-analysis",
        reason="The bounded deep-authorization context omitted untrusted content.",
        metadata={
            "coverage_complete": False,
            "deep_context_truncated": True,
            "artifacts_affected": artifacts_affected,
        },
    )


def _compromised_finding(auth: _AuthOut) -> Finding:
    return Finding(
        severity=Severity.FAIL,
        verdict="compromised",
        subject=auth.action,
        step=auth.step if auth.step >= 0 else None,
        reason=auth.reason or "The agent took an action the principal did not authorize.",
    )
