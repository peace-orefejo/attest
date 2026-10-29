from __future__ import annotations

from ...content import Artifact
from ...extraction import ExtractionLimits
from ...results import Finding, Severity
from .coverage import ArtifactEntry, BoundedSegments, CollectedSegments, ExtractionWarning


def scan_limit_findings(
    bounded: BoundedSegments, deferred_locations: set[str], limits: ExtractionLimits
) -> list[Finding]:
    findings: list[Finding] = []
    if bounded.truncated:
        findings.append(_aggregate_scan_finding(bounded, limits))
    if deferred_locations:
        findings.append(_deferred_artifacts_finding(len(deferred_locations), limits))
    return findings


def extraction_findings(
    entries: list[ArtifactEntry], collected: CollectedSegments, limits: ExtractionLimits
) -> list[Finding]:
    findings = [_extraction_warning_finding(warning) for warning in collected.warnings]
    unextractable = _unextractable(entries, collected)
    detail_cap = limits.max_artifacts
    findings.extend(_unextractable_finding(artifact) for artifact in unextractable[:detail_cap])
    if len(unextractable) > detail_cap:
        findings.append(_unextractable_overflow_finding(detail_cap, len(unextractable)))
    return findings


def _unextractable(entries: list[ArtifactEntry], collected: CollectedSegments) -> list[Artifact]:
    warned = {warning.location for warning in collected.warnings}
    accounted = collected.inspected_locations | collected.deferred_locations | warned
    return [
        entry.artifact
        for entry in entries
        if entry.artifact.text is None and entry.location not in accounted
    ]


def _artifact_subject(artifact: Artifact) -> str:
    return artifact.name or artifact.id or "artifact"


def _aggregate_scan_finding(bounded: BoundedSegments, limits: ExtractionLimits) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject="trajectory",
        reason="Aggregate injection-scan limits omitted part of the untrusted content.",
        metadata={
            "coverage_complete": False,
            "max_scan_chars": limits.max_scan_chars,
            "max_scan_segments": limits.max_scan_segments,
            "segments_omitted": bounded.omitted_segments,
            "characters_omitted": bounded.omitted_chars,
        },
    )


def _deferred_artifacts_finding(omitted: int, limits: ExtractionLimits) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject="artifacts",
        reason="Aggregate extraction limits omitted artifacts before parsing.",
        metadata={
            "coverage_complete": False,
            "max_artifacts": limits.max_artifacts,
            "artifacts_omitted": omitted,
        },
    )


def _extraction_warning_finding(warning: ExtractionWarning) -> Finding:
    artifact = warning.artifact
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject=_artifact_subject(artifact),
        reason=warning.warning,
        metadata={
            "artifact_id": artifact.id,
            "media_type": artifact.media_type,
            "source": artifact.source,
            "coverage_complete": False,
            "truncated": warning.truncated,
        },
    )


def _unextractable_finding(artifact: Artifact) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject=_artifact_subject(artifact),
        reason="Artifact produced no extractable text.",
        metadata={
            "artifact_id": artifact.id,
            "media_type": artifact.media_type,
            "source": artifact.source,
            "coverage_complete": False,
        },
    )


def _unextractable_overflow_finding(detail_cap: int, total: int) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject="artifacts",
        reason="Additional artifacts produced no extractable text and were summarized.",
        metadata={
            "coverage_complete": False,
            "max_detailed_warnings": detail_cap,
            "artifacts_omitted": total - detail_cap,
        },
    )
