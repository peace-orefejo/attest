"""Lookups over the artifact provenance recorded on extracted text segments."""

from __future__ import annotations

from typing import Iterable

from ..content import TextSegment

ARTIFACT_LOCATION_KEY = "artifact_location"


def artifact_location(segment: TextSegment) -> str | None:
    return segment.metadata.get(ARTIFACT_LOCATION_KEY)


def artifact_locations(segments: Iterable[TextSegment]) -> set[str]:
    return {
        location for segment in segments
        if (location := artifact_location(segment)) is not None
    }
