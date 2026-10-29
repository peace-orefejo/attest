"""Bounded extraction of untrusted artifacts into detector-ready text segments."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Iterable

from ..content import Artifact, TextSegment
from .image import _image_parts
from .limits import ExtractionLimits, ExtractionOutcome
from .markup import _html_parts, _xml_parts
from .pdf import _pdf_parts
from .tabular import _csv_parts, _json_parts


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
            [_segment(clipped, artifact, location, step, "artifact_text")]
            if clipped.strip() else [],
            truncated=len(clipped) < len(artifact.text),
            inspected=True,
        )
    try:
        raw = _read_bytes(artifact, limits, allow_paths)
        declared_media = (artifact.media_type or _guess_media(artifact.name)).split(";", 1)[0].lower()
        detected_media = _sniff_media(raw)
        media = detected_media or declared_media
        format_truncated = False
        channel_warnings: list[str] = []
        extraction_artifact = artifact
        if detected_media and detected_media != declared_media:
            extraction_artifact = artifact.model_copy(update={
                "media_type": detected_media,
                "metadata": {**artifact.metadata, "declared_media_type": declared_media},
            })
        if media in {"application/json"}:
            parts = _json_parts(raw)
        elif media in {"text/csv", "text/tab-separated-values"}:
            parts = _csv_parts(
                raw, "\t" if media.endswith("tab-separated-values") else ",",
                limits.max_chars,
            )
        elif media in {"application/xml", "text/xml", "application/xhtml+xml"}:
            parts = _xml_parts(raw)
        elif media == "text/html":
            parts, format_truncated = _html_parts(raw, limits.max_chars)
        elif media == "application/pdf":
            parts, format_truncated = _pdf_parts(raw, limits)
        elif media.startswith("image/"):
            parts, channel_warnings = _image_parts(raw, limits)
        elif media.startswith("text/") or media in {"", "application/octet-stream"}:
            parts = [("text", raw.decode("utf-8", errors="replace"))]
        else:
            return ExtractionOutcome([], f"Unsupported media type: {media or '(unknown)'}")
        outcome = _bounded_segments(parts, extraction_artifact, location, step, limits.max_chars)
        outcome.truncated |= format_truncated
        outcome.inspected = True
        if media.startswith("image/") and channel_warnings:
            outcome.warning = "; ".join(channel_warnings)
        return outcome
    except Exception as exc:
        return ExtractionOutcome([], f"{type(exc).__name__}: {exc}")


def _read_bytes(artifact: Artifact, limits: ExtractionLimits, allow_paths: bool) -> bytes:
    if artifact.data_base64 is not None:
        padding = 2 if artifact.data_base64.endswith("==") else (
            1 if artifact.data_base64.endswith("=") else 0
        )
        estimated = len(artifact.data_base64) * 3 // 4 - padding
        if estimated > limits.max_bytes:
            raise ValueError(f"Artifact exceeds {limits.max_bytes} byte limit")
        raw = base64.b64decode(artifact.data_base64, validate=True)
    elif artifact.path is not None:
        if not allow_paths:
            raise ValueError("Path extraction is disabled; pass allow_paths=True explicitly")
        path = Path(artifact.path)
        if path.stat().st_size > limits.max_bytes:
            raise ValueError(f"Artifact exceeds {limits.max_bytes} byte limit")
        raw = path.read_bytes()
    else:
        raise ValueError("Artifact has no readable content")
    if len(raw) > limits.max_bytes:
        raise ValueError(f"Artifact exceeds {limits.max_bytes} byte limit")
    return raw


def _guess_media(name: str | None) -> str:
    suffix = Path(name or "").suffix.lower()
    return {
        ".json": "application/json", ".csv": "text/csv", ".tsv": "text/tab-separated-values",
        ".xml": "application/xml", ".html": "text/html", ".htm": "text/html",
        ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")


def _sniff_media(raw: bytes) -> str | None:
    """Recognize bounded binary signatures before trusting caller-supplied media types."""
    if raw.startswith(b"%PDF-"):
        return "application/pdf"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    return None


def _bounded_segments(
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
            segments.append(_segment(
                clipped, artifact, f"{location}.{source_kind}", step, source_kind,
                artifact_location=location,
            ))
            used += len(clipped)
    return ExtractionOutcome(segments, truncated=truncated)


def _segment(
    text: str, artifact: Artifact, location: str, step: int | None, source_kind: str,
    *, artifact_location: str | None = None,
) -> TextSegment:
    return TextSegment(
        text=text, location=location, source_kind=source_kind,
        subject=artifact.name or artifact.id or "artifact", step=step,
        metadata={**artifact.metadata,
                  "artifact_id": artifact.id, "media_type": artifact.media_type,
                  "source": artifact.source, "sha256": artifact.sha256,
                  "artifact_location": artifact_location or location},
    )
