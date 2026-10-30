from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

from ...content import Detection, TextSegment
from ...results import Finding
from .coverage import artifact_location
from .detectors import InjectionDetector
from .scan_findings import (
    detection_cap_finding,
    detection_finding,
    detector_failure_finding,
    timeout_finding,
)


class DetectorRun(BaseModel):
    detections: list[Detection] = Field(default_factory=list[Detection])
    overflowed: bool = False
    failure: str | None = None


class ScanOutcome(BaseModel):
    findings: list[Finding] = Field(default_factory=list[Finding])
    incomplete_locations: set[str] = Field(default_factory=set[str])
    detections_emitted: int = 0


def run_detectors(
    segments: Sequence[TextSegment],
    detectors: Sequence[InjectionDetector],
    max_detections: int,
) -> ScanOutcome:
    outcome = ScanOutcome()
    for segment in segments:
        for detector in detectors:
            remaining = max_detections - outcome.detections_emitted
            run = _run_detector(detector, segment, remaining)
            _record(outcome, segment, detector_name(detector), run, max_detections)
            if run.overflowed:
                return outcome
    return outcome


def detector_name(detector: object) -> str:
    name = getattr(detector, "name", None)
    return name if isinstance(name, str) else type(detector).__name__


def _run_detector(detector: InjectionDetector, segment: TextSegment, remaining: int) -> DetectorRun:
    try:
        return _collect(detector.scan(segment), remaining)
    except Exception as exc:
        return DetectorRun(
            failure=f"Detector {detector_name(detector)!r} failed: {type(exc).__name__}: {exc}"
        )


def _collect(raw_detections: Iterable[object], remaining: int) -> DetectorRun:
    run = DetectorRun()
    for raw in raw_detections:
        if len(run.detections) >= remaining:
            run.overflowed = True
            break
        run.detections.append(_as_detection(raw))
    return run


def _as_detection(raw: object) -> Detection:
    return raw if isinstance(raw, Detection) else Detection.model_validate(raw)


def _record(
    outcome: ScanOutcome,
    segment: TextSegment,
    detector: str,
    run: DetectorRun,
    max_detections: int,
) -> None:
    location = artifact_location(segment)
    if run.failure is not None:
        _mark_incomplete(outcome, location)
        outcome.findings.append(detector_failure_finding(segment, detector, run.failure))
        return
    outcome.detections_emitted += len(run.detections)
    for detection in run.detections:
        if detection.verdict == "unscanned_content":
            _mark_incomplete(outcome, location)
            outcome.findings.append(timeout_finding(detection))
        else:
            outcome.findings.append(detection_finding(detection))
    if run.overflowed:
        _mark_incomplete(outcome, location)
        outcome.findings.append(
            detection_cap_finding(segment, detector, max_detections, outcome.detections_emitted)
        )


def _mark_incomplete(outcome: ScanOutcome, location: str | None) -> None:
    if location:
        outcome.incomplete_locations.add(location)
