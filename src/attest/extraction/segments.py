from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from ..content import Artifact, TextSegment
from .parts import ExtractedPart


class BoundedSegments(BaseModel):
    segments: list[TextSegment]
    truncated: bool = False


def bounded_segments(
    parts: Iterable[ExtractedPart],
    artifact: Artifact,
    location: str,
    step: int | None,
    max_chars: int,
) -> BoundedSegments:
    segments: list[TextSegment] = []
    used = 0
    truncated = False
    for part in parts:
        remaining = max_chars - used
        if remaining <= 0:
            truncated = True
            break
        clipped = part.text[:remaining]
        truncated |= len(clipped) < len(part.text)
        if not clipped.strip():
            continue
        segments.append(
            build_segment(
                clipped,
                artifact,
                f"{location}.{part.source_kind}",
                step,
                part.source_kind,
                artifact_location=location,
            )
        )
        used += len(clipped)
    return BoundedSegments(segments=segments, truncated=truncated)


def build_segment(
    text: str,
    artifact: Artifact,
    location: str,
    step: int | None,
    source_kind: str,
    *,
    artifact_location: str | None = None,
) -> TextSegment:
    return TextSegment(
        text=text,
        location=location,
        source_kind=source_kind,
        subject=artifact.name or artifact.id or "artifact",
        step=step,
        metadata={
            **artifact.metadata,
            "artifact_id": artifact.id,
            "media_type": artifact.media_type,
            "source": artifact.source,
            "sha256": artifact.sha256,
            "artifact_location": artifact_location or location,
        },
    )
