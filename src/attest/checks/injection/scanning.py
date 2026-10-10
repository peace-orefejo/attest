"""Running detectors over bounded segments, isolating failures and capping output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ...content import Detection, TextSegment
from ...extraction import ExtractionLimits
from ...results import Finding, Severity
from ...utils import artifact_location
from .findings import detector_name, unscanned_finding
from .models import InjectionDetector


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    incomplete_locations: set[str] = field(default_factory=set)


def scan_segments(
    segments: Sequence[TextSegment],
    detectors: Sequence[InjectionDetector],
    limits: ExtractionLimits,
) -> ScanResult:
    result = ScanResult()
    detections_emitted = 0
    for segment in segments:
        for detector in detectors:
            remaining = limits.max_detections - detections_emitted
            try:
                detections, overflowed = _bounded_detections(detector, segment, remaining)
            except Exception as exc:
                _mark_incomplete(result, segment)
                result.findings.append(unscanned_finding(
                    segment.subject,
                    (f"Detector {detector_name(detector)!r} "
                     f"failed: {type(exc).__name__}: {exc}"),
                    {
                        "coverage_complete": False,
                        "detector": detector_name(detector),
                        "location": segment.location,
                    },
                    step=segment.step,
                ))
                continue
            detections_emitted += len(detections)
            for detection in detections:
                if detection.verdict == "unscanned_content":
                    _mark_incomplete(result, segment)
                result.findings.append(_detection_finding(detection))
            if overflowed:
                _mark_incomplete(result, segment)
                result.findings.append(unscanned_finding(
                    segment.subject,
                    "Detector output reached the total detection cap; scanning stopped.",
                    {
                        "coverage_complete": False,
                        "detector": detector_name(detector),
                        "location": segment.location,
                        "max_detections": limits.max_detections,
                        "detections_emitted": detections_emitted,
                    },
                    step=segment.step,
                ))
                return result
    return result


def _bounded_detections(
    detector: InjectionDetector, segment: TextSegment, remaining: int
) -> tuple[list[Detection], bool]:
    detections: list[Detection] = []
    for raw_detection in detector.scan(segment):
        if len(detections) >= remaining:
            return detections, True
        detections.append(
            raw_detection if isinstance(raw_detection, Detection)
            else Detection.model_validate(raw_detection)
        )
    return detections, False


def _mark_incomplete(result: ScanResult, segment: TextSegment) -> None:
    if location := artifact_location(segment):
        result.incomplete_locations.add(location)


def _detection_finding(detection: Detection) -> Finding:
    if detection.verdict == "unscanned_content":
        return unscanned_finding(
            detection.subject,
            "Regex scanning exceeded its bounded execution time.",
            {
                **detection.metadata,
                "detector": detection.detector,
                "category": detection.category,
                "location": detection.location,
            },
            step=detection.step,
        )
    return Finding(
        severity=Severity.WARN,
        verdict=detection.verdict,
        subject=detection.subject,
        step=detection.step,
        evidence=detection.matched_text,
        reason=_reason(detection),
        metadata={
            **detection.metadata,
            "detector": detection.detector,
            "category": detection.category,
            "location": detection.location,
            "confidence": detection.confidence,
        },
    )


_REASONS = {
    "unicode": "Untrusted content contains hidden or look-alike Unicode characters.",
    "encoded": "Untrusted content contains encoded text that decodes to instruction-like text.",
}


def _reason(detection) -> str:
    return _REASONS.get(detection.detector, "Untrusted content contains instruction-like text.")
