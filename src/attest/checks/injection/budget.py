"""Aggregate character and segment limits applied before detectors run."""

from __future__ import annotations

from ...core import Finding, TextSegment, artifact_location, artifact_locations
from ...extraction import ExtractionLimits
from .findings import unscanned_finding


def bounded_scan_segments(
    segments: list[TextSegment], limits: ExtractionLimits
) -> tuple[list[TextSegment], Finding | None, set[str]]:
    kept: list[TextSegment] = []
    used = 0
    omitted_segments = 0
    omitted_chars = 0
    omitted_locations: set[str] = set()
    for index, segment in enumerate(segments):
        if len(kept) >= limits.max_scan_segments or used >= limits.max_scan_chars:
            omitted_segments += len(segments) - index
            omitted_chars += sum(len(item.text) for item in segments[index:])
            omitted_locations.update(artifact_locations(segments[index:]))
            break
        remaining = limits.max_scan_chars - used
        if len(segment.text) > remaining:
            kept.append(segment.model_copy(update={"text": segment.text[:remaining]}))
            used += remaining
            omitted_chars += len(segment.text) - remaining
            if location := artifact_location(segment):
                omitted_locations.add(location)
            omitted_segments += len(segments) - index - 1
            omitted_chars += sum(len(item.text) for item in segments[index + 1:])
            omitted_locations.update(artifact_locations(segments[index + 1:]))
            break
        kept.append(segment)
        used += len(segment.text)
    if omitted_segments == 0 and omitted_chars == 0:
        return kept, None, omitted_locations
    return kept, unscanned_finding(
        "trajectory",
        "Aggregate injection-scan limits omitted part of the untrusted content.",
        {
            "coverage_complete": False,
            "max_scan_chars": limits.max_scan_chars,
            "max_scan_segments": limits.max_scan_segments,
            "segments_omitted": omitted_segments,
            "characters_omitted": omitted_chars,
        },
    ), omitted_locations
