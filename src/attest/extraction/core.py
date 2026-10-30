"""Bounded extraction of untrusted artifacts into detector-ready text segments."""

from __future__ import annotations

from pydantic import BaseModel

from ..content import Artifact
from ..utils.media import guess_media_type, sniff_media_type
from .image import image_parts
from .limits import ExtractionLimits, ExtractionOutcome
from .markup import html_parts, xml_parts
from .parts import ExtractedPart, ParsedParts
from .reading import read_artifact_bytes
from .segments import bounded_segments, build_segment
from .tabular import csv_parts, json_parts

_XML_MEDIA_TYPES = {"application/xml", "text/xml", "application/xhtml+xml"}
_CSV_MEDIA_TYPES = {"text/csv", "text/tab-separated-values"}
_PLAIN_MEDIA_TYPES = {"", "application/octet-stream"}


class ResolvedMedia(BaseModel):
    media_type: str
    artifact: Artifact


def extract_artifact(
    artifact: Artifact,
    location: str,
    step: int | None,
    *,
    limits: ExtractionLimits = ExtractionLimits(),
    allow_paths: bool = False,
) -> ExtractionOutcome:
    """Extract bounded text segments from one artifact, reporting failures as warnings."""
    if artifact.text is not None:
        return _inline_text_outcome(artifact, location, step, limits.max_chars)
    try:
        return _extract_binary(artifact, location, step, limits, allow_paths)
    except Exception as exc:
        return ExtractionOutcome([], f"{type(exc).__name__}: {exc}")


def _inline_text_outcome(
    artifact: Artifact, location: str, step: int | None, max_chars: int
) -> ExtractionOutcome:
    text = artifact.text or ""
    clipped = text[:max_chars]
    segments = (
        [build_segment(clipped, artifact, location, step, "artifact_text")]
        if clipped.strip()
        else []
    )
    return ExtractionOutcome(segments, truncated=len(clipped) < len(text), inspected=True)


def _extract_binary(
    artifact: Artifact,
    location: str,
    step: int | None,
    limits: ExtractionLimits,
    allow_paths: bool,
) -> ExtractionOutcome:
    raw = read_artifact_bytes(artifact, limits.max_bytes, allow_paths)
    resolved = _resolve_media(artifact, raw)
    parsed = _parse_parts(raw, resolved.media_type, limits)
    if parsed is None:
        return ExtractionOutcome(
            [], f"Unsupported media type: {resolved.media_type or '(unknown)'}"
        )
    bounded = bounded_segments(parsed.parts, resolved.artifact, location, step, limits.max_chars)
    return ExtractionOutcome(
        bounded.segments,
        warning="; ".join(parsed.warnings) or None,
        truncated=bounded.truncated or parsed.truncated,
        inspected=True,
    )


def _resolve_media(artifact: Artifact, raw: bytes) -> ResolvedMedia:
    declared = (artifact.media_type or guess_media_type(artifact.name)).split(";", 1)[0].lower()
    detected = sniff_media_type(raw)
    if not detected:
        return ResolvedMedia(media_type=declared, artifact=artifact)
    if detected == declared:
        return ResolvedMedia(media_type=detected, artifact=artifact)
    relabeled = artifact.model_copy(
        update={
            "media_type": detected,
            "metadata": {**artifact.metadata, "declared_media_type": declared},
        }
    )
    return ResolvedMedia(media_type=detected, artifact=relabeled)


def _parse_parts(raw: bytes, media: str, limits: ExtractionLimits) -> ParsedParts | None:
    if media == "application/json":
        return json_parts(raw)
    if media in _CSV_MEDIA_TYPES:
        delimiter = "\t" if media.endswith("tab-separated-values") else ","
        return csv_parts(raw, delimiter, limits.max_chars)
    if media in _XML_MEDIA_TYPES:
        return xml_parts(raw)
    if media == "text/html":
        return html_parts(raw, limits.max_chars)
    if media == "application/pdf":
        from .pdf import pdf_parts

        return pdf_parts(raw, limits)
    if media.startswith("image/"):
        return image_parts(raw, limits)
    if media.startswith("text/") or media in _PLAIN_MEDIA_TYPES:
        text = raw.decode("utf-8", errors="replace")
        return ParsedParts(parts=[ExtractedPart(source_kind="text", text=text)])
    return None
