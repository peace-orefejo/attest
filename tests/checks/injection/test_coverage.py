"""Detector isolation, detection caps, and coverage accounting."""

from attest import Artifact
from attest.checks.injection import (
    RegexDetector,
    RegexPattern,
    check_injection,
)
from attest.extraction import ExtractionLimits
from attest.trajectory import Trajectory

from ._helpers import _InfiniteDetector, _traj


def test_detector_failure_isolated_as_incomplete_coverage():
    class BrokenDetector:
        name = "broken"

        def scan(self, segment):
            raise RuntimeError("boom")

    trajectory = Trajectory(task="inspect", final_answer="done", artifacts=[
        Artifact(name="payload.txt", source="user_upload", text="safe content")
    ])
    result = check_injection(trajectory, detectors=[BrokenDetector()])
    finding = next(f for f in result.findings if f.verdict == "unscanned_content")
    assert finding.metadata["detector"] == "broken"
    assert finding.metadata["location"] == "artifacts[0]"
    assert "RuntimeError: boom" in finding.reason
    assert result.metadata["coverage_complete"] is False
    assert result.metadata["artifacts_scanned"] == 0
    assert result.metadata["artifacts_failed"] == 1


def test_malformed_detector_output_isolated_as_incomplete_coverage():
    class MalformedDetector:
        name = "malformed"

        def scan(self, segment):
            return [None]

    trajectory = Trajectory(task="inspect", final_answer="done", artifacts=[
        Artifact(name="payload.txt", source="user_upload", text="safe content")
    ])
    result = check_injection(trajectory, detectors=[MalformedDetector()])
    finding = next(f for f in result.findings if f.verdict == "unscanned_content")
    assert finding.metadata["detector"] == "malformed"
    assert "ValidationError" in finding.reason
    assert result.metadata["coverage_complete"] is False
    assert result.metadata["artifacts_scanned"] == 0
    assert result.metadata["artifacts_failed"] == 1


def test_regex_timeout_marks_artifact_counter_incomplete():
    detector = RegexDetector(
        [RegexPattern("catastrophic", r"(a+)+b$")],
        match_timeout_ms=1,
        segment_budget_ms=5,
    )
    trajectory = Trajectory(task="inspect", final_answer="done", artifacts=[
        Artifact(name="payload.txt", source="user_upload", text="a" * 20_000)
    ])
    result = check_injection(trajectory, detectors=[detector])
    assert result.metadata["coverage_complete"] is False
    assert result.metadata["artifacts_scanned"] == 0
    assert result.metadata["artifacts_failed"] == 1


def test_detection_cap_bounds_unbounded_detector():
    result = check_injection(
        _traj("untrusted text to scan"),
        detectors=[_InfiniteDetector()],
        extraction_limits=ExtractionLimits(max_detections=50),
    )
    suspicious = [f for f in result.findings if f.verdict == "suspicious"]
    assert len(suspicious) == 50
    cap = next(
        f for f in result.findings
        if f.verdict == "unscanned_content" and f.metadata.get("max_detections") == 50
    )
    assert cap.metadata["detections_emitted"] == 50
    assert result.metadata["coverage_complete"] is False


def test_disabled_extraction_warnings_are_bounded_and_summarized():
    trajectory = Trajectory(task="inspect", final_answer="done", artifacts=[
        Artifact(id=f"bin{i}", media_type="application/octet-stream", data_base64="AAAA")
        for i in range(1_000)
    ])
    result = check_injection(
        trajectory, extract_files=False,
        extraction_limits=ExtractionLimits(max_artifacts=10),
    )
    detailed = [
        f for f in result.findings
        if f.reason == "Artifact produced no extractable text."
    ]
    assert len(detailed) == 10
    summary = next(f for f in result.findings if f.metadata.get("artifacts_omitted"))
    assert summary.metadata["artifacts_omitted"] == 990
    assert summary.metadata["max_detailed_warnings"] == 10
    assert result.metadata["coverage_complete"] is False
