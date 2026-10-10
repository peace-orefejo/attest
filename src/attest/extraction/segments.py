"""Conversion of extracted text parts into character-bounded text segments."""

from __future__ import annotations

from typing import Iterable

from ..content import Artifact, TextSegment
from ..utils import ARTIFACT_LOCATION_KEY, artifact_subject
from .outcome import ExtractionOutcome


def bounded_segments(
    parts: Iterable[tuple[str, str]], artifact: Artifact, location: str,
    step: int | None, max_chars: int,
) -> ExtractionOutcome:
    segments, used, truncated = [], 0, False
    for source_kind, text in parts:
        remaining = max_chars - used
        if remaining <= 0:
            truncated = True
            break
        clipped = text[:remaining]
        truncated |= len(clipped) < len(text)
        if clipped.strip():
            segments.append(make_segment(
                clipped, artifact, f"{location}.{source_kind}", step, source_kind,
                artifact_location=location,
            ))
            used += len(clipped)
    return ExtractionOutcome(segments, truncated=truncated)


def make_segment(
    text: str, artifact: Artifact, location: str, step: int | None, source_kind: str,
    *, artifact_location: str | None = None,
) -> TextSegment:
    return TextSegment(
        text=text, location=location, source_kind=source_kind,
        subject=artifact_subject(artifact), step=step,
        metadata={**artifact.metadata,
                  "artifact_id": artifact.id, "media_type": artifact.media_type,
                  "source": artifact.source, "sha256": artifact.sha256,
                  ARTIFACT_LOCATION_KEY: artifact_location or location},
    )
