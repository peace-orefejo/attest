"""Findings for artifacts that were deferred, partially extracted, or produced no text."""

from __future__ import annotations

from ...extraction import ExtractionLimits
from ...results import Finding
from ...utils import artifact_subject
from .collect import CollectedSegments
from .findings import unscanned_finding


def deferred_artifacts_finding(
    deferred_count: int, limits: ExtractionLimits
) -> Finding:
    return unscanned_finding(
        "artifacts",
        "Aggregate extraction limits omitted artifacts before parsing.",
        {
            "coverage_complete": False,
            "max_artifacts": limits.max_artifacts,
            "artifacts_omitted": deferred_count,
        },
    )


def extraction_coverage_findings(
    collected: CollectedSegments, limits: ExtractionLimits
) -> list[Finding]:
    findings: list[Finding] = []
    warning_locations = {entry[1] for entry in collected.extraction_warnings}
    for artifact, location, warning, truncated in collected.extraction_warnings:
        findings.append(unscanned_finding(
            artifact_subject(artifact), warning,
            {"artifact_id": artifact.id, "media_type": artifact.media_type,
             "source": artifact.source, "coverage_complete": False,
             "truncated": truncated},
        ))
    unextractable = [
        (artifact, location) for artifact, location, _ in collected.artifact_entries
        if (artifact.text is None and location not in collected.inspected_locations
            and location not in collected.deferred_locations
            and location not in warning_locations)
    ]
    detail_cap = limits.max_artifacts
    for artifact, location in unextractable[:detail_cap]:
        findings.append(unscanned_finding(
            artifact_subject(artifact),
            "Artifact produced no extractable text.",
            {
                "artifact_id": artifact.id,
                "media_type": artifact.media_type,
                "source": artifact.source,
                "coverage_complete": False,
            },
        ))
    if len(unextractable) > detail_cap:
        findings.append(unscanned_finding(
            "artifacts",
            "Additional artifacts produced no extractable text and were summarized.",
            {
                "coverage_complete": False,
                "max_detailed_warnings": detail_cap,
                "artifacts_omitted": len(unextractable) - detail_cap,
            },
        ))
    return findings
