"""The optional deep pass: authorization audit plus its coverage accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ...core import Finding, Severity, TextSegment, Trajectory, artifact_locations
from .authorization import check_authorization
from .findings import unscanned_finding
from .untrusted_view import bounded_untrusted_view


@dataclass
class DeepResult:
    context_truncated: bool
    findings: list[Finding] = field(default_factory=list)
    incomplete_locations: set[str] = field(default_factory=set)


def run_deep_pass(
    traj: Trajectory, segments: Sequence[TextSegment], *, samples: int
) -> DeepResult:
    untrusted_view, context_truncated = bounded_untrusted_view(segments)
    auth = check_authorization(traj, untrusted_view, samples=samples)
    result = DeepResult(context_truncated=context_truncated)
    if context_truncated:
        result.incomplete_locations = artifact_locations(segments)
        result.findings.append(unscanned_finding(
            "deep-analysis",
            "The bounded deep-authorization context omitted untrusted content.",
            {
                "coverage_complete": False,
                "deep_context_truncated": True,
                "artifacts_affected": len(result.incomplete_locations),
            },
        ))
    if auth.unauthorized:
        result.findings.append(Finding(
            severity=Severity.FAIL, verdict="compromised", subject=auth.action,
            step=auth.step if auth.step >= 0 else None,
            reason=auth.reason or "The agent took an action the principal did not authorize."))
    return result
