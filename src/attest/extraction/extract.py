"""Entry point that turns one artifact into bounded, provenance-tagged text segments."""

from __future__ import annotations

from ..core import Artifact
from .dispatch import parse_parts
from .limits import ExtractionLimits
from .media import guess_media, sniff_media
from .outcome import ExtractionOutcome
from .segments import bounded_segments, make_segment
from .sources import read_bytes


def extract_artifact(
    artifact: Artifact,
    location: str,
    step: int | None,
    *,
    limits: ExtractionLimits = ExtractionLimits(),
    allow_paths: bool = False,
) -> ExtractionOutcome:
    if artifact.text is not None:
        clipped = artifact.text[:limits.max_chars]
        return ExtractionOutcome(
            [make_segment(clipped, artifact, location, step, "artifact_text")]
            if clipped.strip() else [],
            truncated=len(clipped) < len(artifact.text),
            inspected=True,
        )
    try:
        raw = read_bytes(artifact, limits, allow_paths)
        declared_media = (artifact.media_type or guess_media(artifact.name)).split(";", 1)[0].lower()
        detected_media = sniff_media(raw)
        media = detected_media or declared_media
        extraction_artifact = artifact
        if detected_media and detected_media != declared_media:
            extraction_artifact = artifact.model_copy(update={
                "media_type": detected_media,
                "metadata": {**artifact.metadata, "declared_media_type": declared_media},
            })
        parsed = parse_parts(raw, media, limits)
        if parsed is None:
            return ExtractionOutcome([], f"Unsupported media type: {media or '(unknown)'}")
        outcome = bounded_segments(
            parsed.parts, extraction_artifact, location, step, limits.max_chars
        )
        outcome.truncated |= parsed.truncated
        outcome.inspected = True
        if media.startswith("image/") and parsed.warnings:
            outcome.warning = "; ".join(parsed.warnings)
        return outcome
    except Exception as exc:
        return ExtractionOutcome([], f"{type(exc).__name__}: {exc}")
