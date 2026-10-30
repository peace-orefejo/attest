from __future__ import annotations

from collections.abc import Sequence

from ...extraction import ExtractionLimits
from ...results import CheckResult, Severity
from ...trajectory import Trajectory
from .coverage import ArtifactEntry, artifact_entries, bound_scan_segments, collect_segments
from .coverage_findings import extraction_findings, scan_limit_findings
from .deep import DeepOutcome, run_deep_check
from .defaults import DEFAULT_DETECTORS
from .detectors import InjectionDetector
from .scanning import run_detectors
from .summary import result_metadata, summarize


def check_injection(
    traj: Trajectory,
    *,
    deep: bool = False,
    samples: int = 3,
    detectors: Sequence[InjectionDetector] = DEFAULT_DETECTORS,
    extract_files: bool = True,
    allow_paths: bool = False,
    extraction_limits: ExtractionLimits = ExtractionLimits(),
) -> CheckResult:
    """Scan untrusted text with configured detectors, then optionally check its effect."""
    if not detectors:
        raise ValueError("At least one injection detector is required.")
    entries = artifact_entries(traj)
    collected = collect_segments(
        traj,
        entries,
        extract_files=extract_files,
        allow_paths=allow_paths,
        limits=extraction_limits,
    )
    bounded = bound_scan_segments(collected.segments, extraction_limits)
    scan = run_detectors(bounded.segments, detectors, extraction_limits.max_detections)
    deep_outcome = run_deep_check(traj, bounded.segments, samples) if deep else DeepOutcome()

    findings = [
        *scan_limit_findings(bounded, collected.deferred_locations, extraction_limits),
        *scan.findings,
        *extraction_findings(entries, collected, extraction_limits),
        *deep_outcome.findings,
    ]
    incomplete = (
        bounded.omitted_locations
        | collected.deferred_locations
        | scan.incomplete_locations
        | deep_outcome.incomplete_locations
    )
    return CheckResult(
        check="injection",
        passed=all(f.severity is not Severity.FAIL for f in findings),
        score=None,
        summary=summarize(findings, deep),
        findings=findings,
        metadata=result_metadata(
            findings,
            segments_scanned=len(bounded.segments),
            artifacts_total=len(entries),
            artifacts_scanned=_count_scanned(entries, collected.inspected_locations, incomplete),
            deep_context_truncated=deep_outcome.context_truncated if deep else None,
        ),
    )


def _count_scanned(entries: list[ArtifactEntry], inspected: set[str], incomplete: set[str]) -> int:
    return sum(
        entry.location in inspected and entry.location not in incomplete for entry in entries
    )
