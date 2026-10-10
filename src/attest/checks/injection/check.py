"""The ``check_injection`` entry point, orchestrating collection, scanning, and the deep pass."""

from __future__ import annotations

from typing import Sequence

from ...extraction import ExtractionLimits
from ...core import CheckResult, Finding, Trajectory
from .budget import bounded_scan_segments
from .collect import collect_segments
from .coverage import deferred_artifacts_finding, extraction_coverage_findings
from .deep import run_deep_pass
from .models import InjectionDetector
from .detectors import DEFAULT_DETECTORS
from .scanning import scan_segments
from .verdict import build_result


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
    findings: list[Finding] = []

    collected = collect_segments(
        traj, extract_files=extract_files, allow_paths=allow_paths, limits=extraction_limits
    )
    segments, aggregate_warning, omitted_locations = bounded_scan_segments(
        collected.segments, extraction_limits
    )
    omitted_locations.update(collected.deferred_locations)
    if aggregate_warning is not None:
        findings.append(aggregate_warning)
    if collected.deferred_locations:
        findings.append(deferred_artifacts_finding(
            len(collected.deferred_locations), extraction_limits
        ))

    scan = scan_segments(segments, detectors, extraction_limits)
    findings.extend(scan.findings)
    incomplete_locations = scan.incomplete_locations
    findings.extend(extraction_coverage_findings(collected, extraction_limits))

    deep_context_truncated = False
    if deep:
        deep_result = run_deep_pass(traj, segments, samples=samples)
        incomplete_locations.update(deep_result.incomplete_locations)
        findings.extend(deep_result.findings)
        deep_context_truncated = deep_result.context_truncated

    return build_result(
        findings,
        deep=deep,
        segments=segments,
        artifact_entries=collected.artifact_entries,
        inspected_locations=collected.inspected_locations,
        omitted_locations=omitted_locations,
        incomplete_locations=incomplete_locations,
        deep_context_truncated=deep_context_truncated,
    )
