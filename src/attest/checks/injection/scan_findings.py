from __future__ import annotations

from ...content import Detection, TextSegment
from ...results import Finding, Severity

DEFAULT_REASON = "Untrusted content contains instruction-like text."
DETECTOR_REASONS = {
    "unicode": "Untrusted content contains hidden or look-alike Unicode characters.",
    "encoded": "Untrusted content contains encoded text that decodes to instruction-like text.",
}


def detection_finding(detection: Detection) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict=detection.verdict,
        subject=detection.subject,
        step=detection.step,
        evidence=detection.matched_text,
        reason=DETECTOR_REASONS.get(detection.detector, DEFAULT_REASON),
        metadata={
            **detection.metadata,
            "detector": detection.detector,
            "category": detection.category,
            "location": detection.location,
            "confidence": detection.confidence,
        },
    )


def timeout_finding(detection: Detection) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject=detection.subject,
        step=detection.step,
        reason="Regex scanning exceeded its bounded execution time.",
        metadata={
            **detection.metadata,
            "detector": detection.detector,
            "category": detection.category,
            "location": detection.location,
        },
    )


def detector_failure_finding(segment: TextSegment, detector: str, reason: str) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject=segment.subject,
        step=segment.step,
        reason=reason,
        metadata={
            "coverage_complete": False,
            "detector": detector,
            "location": segment.location,
        },
    )


def detection_cap_finding(
    segment: TextSegment, detector: str, max_detections: int, detections_emitted: int
) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject=segment.subject,
        step=segment.step,
        reason="Detector output reached the total detection cap; scanning stopped.",
        metadata={
            "coverage_complete": False,
            "detector": detector,
            "location": segment.location,
            "max_detections": max_detections,
            "detections_emitted": detections_emitted,
        },
    )
