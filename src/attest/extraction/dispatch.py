"""Routing of raw artifact bytes to the parser for their resolved media type."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .formats import csv_parts, html_parts, image_parts, json_parts, pdf_parts, xml_parts
from .limits import ExtractionLimits


@dataclass
class ParsedParts:
    parts: Iterable[tuple[str, str]]
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


def parse_parts(raw: bytes, media: str, limits: ExtractionLimits) -> ParsedParts | None:
    """Return the parsed parts for ``media``, or ``None`` when it is unsupported."""
    if media in {"application/json"}:
        return ParsedParts(json_parts(raw))
    if media in {"text/csv", "text/tab-separated-values"}:
        return ParsedParts(csv_parts(
            raw, "\t" if media.endswith("tab-separated-values") else ",",
            limits.max_chars,
        ))
    if media in {"application/xml", "text/xml", "application/xhtml+xml"}:
        return ParsedParts(xml_parts(raw))
    if media == "text/html":
        parts, truncated = html_parts(raw, limits.max_chars)
        return ParsedParts(parts, truncated=truncated)
    if media == "application/pdf":
        parts, truncated = pdf_parts(raw, limits)
        return ParsedParts(parts, truncated=truncated)
    if media.startswith("image/"):
        parts, warnings = image_parts(raw, limits)
        return ParsedParts(parts, warnings=warnings)
    if media.startswith("text/") or media in {"", "application/octet-stream"}:
        return ParsedParts([("text", raw.decode("utf-8", errors="replace"))])
    return None
