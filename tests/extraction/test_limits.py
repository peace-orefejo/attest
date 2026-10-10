"""ExtractionLimits validation and per-artifact size limits."""

import pytest

from attest import Artifact, Trajectory
from attest.checks.injection import check_injection
from attest.extraction import ExtractionLimits, extract_artifact

from ._helpers import _artifact


@pytest.mark.parametrize(
    "name,value",
    [
        ("max_bytes", 0),
        ("max_chars", -1),
        ("max_scan_chars", 0),
        ("max_scan_segments", False),
        ("max_artifacts", 0),
        ("max_pdf_pages", -1),
        ("max_pdf_decoded_bytes", 0),
        ("max_image_pixels", False),
        ("ocr_timeout_seconds", 1.5),
    ],
)
def test_extraction_limits_require_positive_integers(name, value):
    with pytest.raises(ValueError, match=f"{name} must be a positive integer"):
        ExtractionLimits(**{name: value})


def test_size_limit_fails_closed():
    artifact = _artifact(b"x" * 100, "large.txt", "text/plain")
    outcome = extract_artifact(
        artifact, "artifacts[0]", None, limits=ExtractionLimits(max_bytes=10)
    )
    assert not outcome.segments
    assert "exceeds" in outcome.warning


@pytest.mark.parametrize("raw", [b"a", b"ab", b"abc"])
def test_base64_artifact_at_exact_byte_limit_is_accepted(raw):
    artifact = _artifact(raw, "exact.txt", "text/plain")
    outcome = extract_artifact(
        artifact, "artifacts[0]", None, limits=ExtractionLimits(max_bytes=len(raw))
    )
    assert outcome.warning is None
    assert outcome.inspected is True
    assert [segment.text for segment in outcome.segments] == [raw.decode()]


def test_direct_text_artifact_obeys_character_limit():
    artifact = Artifact(
        name="large.txt", media_type="text/plain", source="user_upload",
        text="safe " * 1_000,
    )
    limits = ExtractionLimits(max_chars=10)
    outcome = extract_artifact(artifact, "artifacts[0]", None, limits=limits)
    result = check_injection(
        Trajectory(task="inspect", final_answer="done", artifacts=[artifact]),
        extraction_limits=limits,
    )
    assert len(outcome.segments[0].text) == 10
    assert outcome.truncated is True
    assert result.metadata["coverage_complete"] is False
    assert any(f.verdict == "unscanned_content" for f in result.findings)
