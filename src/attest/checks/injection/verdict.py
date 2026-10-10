"""Assembly of the final injection CheckResult, its summary, and coverage metadata."""

from __future__ import annotations

from typing import Sequence

from ...core import CheckResult, Finding, Severity, TextSegment
from .collect import ArtifactEntry


def summarize(findings: list[Finding], deep: bool) -> str:
    if not findings:
        return ("No payloads detected and no unauthorized actions found."
                if deep else "No injection payloads detected in tool outputs.")
    payloads = [f for f in findings if f.verdict in {"suspicious", "possible_injection"}]
    compromised = [f for f in findings if f.verdict == "compromised"]
    unscanned = [f for f in findings if f.verdict == "unscanned_content"]
    parts: list[str] = []
    if payloads:
        parts.append(f"{len(payloads)} untrusted segment(s) carry instruction-like content.")
    if compromised:
        parts.append(f"{len(compromised)} UNAUTHORIZED action(s) — likely a successful injection.")
    elif payloads and deep:
        parts.append("But the agent did not take any unauthorized action.")
    elif payloads:
        parts.append("Run with deep=True to check whether the agent acted on them.")
    if unscanned:
        parts.append(f"{len(unscanned)} artifact(s) could not be scanned as text.")
    return " ".join(parts)


def build_result(
    findings: list[Finding],
    *,
    deep: bool,
    segments: Sequence[TextSegment],
    artifact_entries: Sequence[ArtifactEntry],
    inspected_locations: set[str],
    omitted_locations: set[str],
    incomplete_locations: set[str],
    deep_context_truncated: bool,
) -> CheckResult:
    unscanned_count = sum(f.verdict == "unscanned_content" for f in findings)
    patterns_attempted = sum(
        int(f.metadata.get("patterns_attempted", 0)) for f in findings
    )
    patterns_skipped = sum(
        int(f.metadata.get("patterns_skipped", 0)) for f in findings
    )
    artifacts_total = len(artifact_entries)
    artifacts_scanned = sum(
        location in inspected_locations
        and location not in omitted_locations
        and location not in incomplete_locations
        for _, location, _ in artifact_entries
    )
    return CheckResult(
        check="injection",
        passed=all(f.severity is not Severity.FAIL for f in findings),
        score=None,
        summary=summarize(findings, deep),
        findings=findings,
        metadata={
            "segments_scanned": len(segments),
            "artifacts_total": artifacts_total,
            "artifacts_scanned": artifacts_scanned,
            "artifacts_failed": artifacts_total - artifacts_scanned,
            "unscanned_count": unscanned_count,
            "coverage_complete": unscanned_count == 0,
            "patterns_attempted_before_timeout": patterns_attempted,
            "patterns_skipped_after_timeout": patterns_skipped,
            "deep_context_truncated": deep_context_truncated if deep else None,
        },
    )
