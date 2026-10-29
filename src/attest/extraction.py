"""Bounded extraction of untrusted artifacts into detector-ready text segments."""

from __future__ import annotations

import base64
import csv
import io
import json
import zlib
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from .content import Artifact, TextSegment


@dataclass(frozen=True)
class ExtractionLimits:
    max_bytes: int = 5_000_000
    max_chars: int = 200_000
    max_scan_chars: int = 1_000_000
    max_scan_segments: int = 500
    max_artifacts: int = 100
    max_detections: int = 1_000
    max_pdf_pages: int = 50
    max_pdf_decoded_bytes: int = 5_000_000
    max_image_pixels: int = 25_000_000
    ocr_timeout_seconds: int = 10

    def __post_init__(self) -> None:
        for name in (
            "max_bytes", "max_chars", "max_scan_chars", "max_scan_segments",
            "max_artifacts", "max_detections",
            "max_pdf_pages", "max_pdf_decoded_bytes", "max_image_pixels",
            "ocr_timeout_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass
class ExtractionOutcome:
    segments: list[TextSegment]
    warning: str | None = None
    truncated: bool = False
    inspected: bool = False


class _HTMLText(HTMLParser):
    def __init__(self, max_chars: int) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[tuple[str, str]] = []
        self.max_chars = max_chars
        self.used = 0
        self.truncated = False

    def _append(self, source_kind: str, value: str) -> None:
        if not value.strip():
            return
        remaining = self.max_chars - self.used
        if remaining <= 0:
            self.truncated = True
            return
        clipped = value[:remaining]
        self.parts.append((source_kind, clipped))
        self.used += len(clipped)
        self.truncated |= len(clipped) < len(value)

    def handle_data(self, data: str) -> None:
        self._append("html.text", data)

    def handle_comment(self, data: str) -> None:
        self._append("html.comment", data)

    def handle_starttag(self, tag: str, attrs) -> None:
        for name, value in attrs:
            if value and name.lower() in {"alt", "title", "aria-label"}:
                self._append(f"html.attribute.{name}", value)


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


def _json_parts(raw: bytes) -> Iterable[tuple[str, str]]:
    value = json.loads(raw)
    def walk(item, path: str) -> Iterable[tuple[str, str]]:
        if isinstance(item, dict):
            for key, child in item.items():
                yield from walk(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                yield from walk(child, f"{path}[{index}]")
        elif isinstance(item, str):
            yield (f"json{path}", item)
    return walk(value, "$")


def _csv_parts(
    raw: bytes, delimiter: str, max_chars: int
) -> Iterable[tuple[str, str]]:
    """Parse the default CSV dialect without mutating csv.field_size_limit globally."""
    text = raw.decode("utf-8", errors="replace")

    def parts() -> Iterable[tuple[str, str]]:
        row = column = index = 0
        field: list[str] = []
        in_quotes = False
        field_limit = max(0, max_chars) + 1

        def value() -> str:
            return "".join(field)

        while index < len(text):
            char = text[index]
            if in_quotes:
                if char == '"':
                    if index + 1 < len(text) and text[index + 1] == '"':
                        if len(field) < field_limit:
                            field.append('"')
                        index += 2
                        continue
                    in_quotes = False
                elif len(field) < field_limit:
                    field.append(char)
            elif char == '"' and not field:
                in_quotes = True
            elif char == delimiter:
                cell = value()
                if cell.strip():
                    yield (f"csv.row[{row}].cell[{column}]", cell)
                field.clear()
                column += 1
            elif char in "\r\n":
                cell = value()
                if cell.strip():
                    yield (f"csv.row[{row}].cell[{column}]", cell)
                field.clear()
                row += 1
                column = 0
                if char == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
                    index += 1
            elif len(field) < field_limit:
                field.append(char)
            index += 1

        if in_quotes:
            raise csv.Error("unexpected end of data")
        cell = value()
        if cell.strip():
            yield (f"csv.row[{row}].cell[{column}]", cell)

    return parts()


def _xml_parts(raw: bytes) -> Iterable[tuple[str, str]]:
    from defusedxml import ElementTree
    root = ElementTree.fromstring(raw)
    def parts() -> Iterable[tuple[str, str]]:
        for index, element in enumerate(root.iter()):
            if element.text and element.text.strip():
                yield (f"xml.element[{index}].text", element.text)
            for name, value in element.attrib.items():
                yield (f"xml.element[{index}].attribute.{name}", value)
    return parts()


def _html_parts(raw: bytes, max_chars: int) -> tuple[list[tuple[str, str]], bool]:
    parser = _HTMLText(max_chars)
    parser.feed(raw.decode("utf-8", errors="replace"))
    return parser.parts, parser.truncated


def _pdf_parts(
    raw: bytes, limits: ExtractionLimits
) -> tuple[Iterable[tuple[str, str]], bool]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw), strict=False)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF cannot be inspected")
    truncated = len(reader.pages) > limits.max_pdf_pages
    def parts() -> Iterable[tuple[str, str]]:
        decoded_used = 0
        seen_streams: set[int] = set()
        for index, page in enumerate(reader.pages[:limits.max_pdf_pages]):
            decoded_used = _check_pdf_page_budget(
                page, decoded_used, limits.max_pdf_decoded_bytes, seen_streams
            )
            text = page.extract_text() or ""
            if text.strip():
                yield (f"pdf.page[{index + 1}]", text)
    return parts(), truncated


def _check_pdf_page_budget(page, used: int, limit: int, seen: set[int]) -> int:
    """Bound content, font maps, and form streams read by pypdf text extraction."""
    used = _check_pdf_stream_refs(page.get("/Contents"), used, limit, seen)
    return _check_pdf_resources(page.get("/Resources"), used, limit, seen)


def _check_pdf_resources(resources_ref, used: int, limit: int, seen: set[int]) -> int:
    if resources_ref is None:
        return used
    resources = resources_ref.get_object()
    fonts_ref = resources.get("/Font")
    if fonts_ref is not None:
        for font_ref in fonts_ref.get_object().values():
            font = font_ref.get_object()
            used = _check_pdf_stream_refs(font.get("/ToUnicode"), used, limit, seen)
    xobjects_ref = resources.get("/XObject")
    if xobjects_ref is not None:
        for xobject_ref in xobjects_ref.get_object().values():
            xobject = xobject_ref.get_object()
            if str(xobject.get("/Subtype")) != "/Form":
                continue
            used = _check_pdf_stream_refs(xobject, used, limit, seen)
            used = _check_pdf_resources(xobject.get("/Resources"), used, limit, seen)
    return used


def _check_pdf_stream_refs(value, used: int, limit: int, seen: set[int]) -> int:
    if value is None:
        return used
    resolved = value.get_object()
    if isinstance(resolved, list):
        for item in resolved:
            used = _check_pdf_stream_refs(item, used, limit, seen)
        return used
    identity = id(resolved)
    if identity in seen:
        return used
    seen.add(identity)
    remaining = limit - used
    if remaining < 0:
        raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
    decoded_size = len(_bounded_pdf_decode(resolved, remaining, limit))
    return used + decoded_size


def _bounded_pdf_decode(stream, remaining: int, limit: int) -> bytes:
    filters = stream.get("/Filter")
    if filters is None:
        names: list[str] = []
    else:
        resolved_filters = filters.get_object()
        names = ([str(item) for item in resolved_filters]
                 if isinstance(resolved_filters, list) else [str(resolved_filters)])
    data = stream._data
    for name in names:
        if name in {"/ASCII85Decode", "/A85"}:
            data = base64.a85decode(data, adobe=True)
        elif name in {"/ASCIIHexDecode", "/AHx"}:
            compact = b"".join(data.split()).removesuffix(b">")
            if len(compact) % 2:
                compact += b"0"
            data = bytes.fromhex(compact.decode("ascii"))
        elif name in {"/FlateDecode", "/Fl"}:
            decoder = zlib.decompressobj()
            data = decoder.decompress(data, remaining + 1)
            if len(data) > remaining or not decoder.eof:
                raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
        elif name in {"/RunLengthDecode", "/RL"}:
            data = _bounded_run_length_decode(data, remaining, limit)
        else:
            raise ValueError(f"PDF content filter cannot be bounded safely: {name}")
        if len(data) > remaining:
            raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
    if len(data) > remaining:
        raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
    return data


def _bounded_run_length_decode(data: bytes, remaining: int, limit: int) -> bytes:
    decoded = bytearray()
    index = 0
    while index < len(data):
        length = data[index]
        index += 1
        if length == 128:
            break
        if length < 128:
            count = length + 1
            decoded.extend(data[index:index + count])
            index += count
        else:
            if index >= len(data):
                raise ValueError("Malformed PDF RunLength stream")
            decoded.extend(data[index:index + 1] * (257 - length))
            index += 1
        if len(decoded) > remaining:
            raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
    return bytes(decoded)


def _image_parts(
    raw: bytes, limits: ExtractionLimits
) -> tuple[list[tuple[str, str]], list[str]]:
    from PIL import Image
    image = Image.open(io.BytesIO(raw))
    if image.width * image.height > limits.max_image_pixels:
        raise ValueError("Image exceeds pixel limit")
    image.load()
    parts: list[tuple[str, str]] = []
    warnings: list[str] = []
    # Each channel degrades on its own: a missing optional dependency must not
    # silence the channels that are still available. A scanner that quietly
    # stops scanning is worse than one that says what it could not read.
    try:
        import pytesseract
        text = pytesseract.image_to_string(image, timeout=limits.ocr_timeout_seconds)
        if text.strip():
            parts.append(("image.ocr", text))
    except Exception as exc:
        warnings.append(f"OCR unavailable: {type(exc).__name__}: {exc}")
    try:
        import zxingcpp
        for index, barcode in enumerate(zxingcpp.read_barcodes(image)):
            if barcode.text:
                parts.append((f"image.qr[{index}]", barcode.text))
    except Exception as exc:
        warnings.append(f"QR decoding failed: {type(exc).__name__}: {exc}")
    for key, value in image.getexif().items():
        if isinstance(value, str) and value.strip():
            parts.append((f"image.metadata[{key}]", value))
    return parts, warnings


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
