from __future__ import annotations

import base64
import io
import zlib
from collections.abc import Iterable

from .limits import ExtractionLimits


def _pdf_parts(raw: bytes, limits: ExtractionLimits) -> tuple[Iterable[tuple[str, str]], bool]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw), strict=False)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF cannot be inspected")
    truncated = len(reader.pages) > limits.max_pdf_pages

    def parts() -> Iterable[tuple[str, str]]:
        decoded_used = 0
        seen_streams: set[int] = set()
        for index, page in enumerate(reader.pages[: limits.max_pdf_pages]):
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
        names = (
            [str(item) for item in resolved_filters]
            if isinstance(resolved_filters, list)
            else [str(resolved_filters)]
        )
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
            decoded.extend(data[index : index + count])
            index += count
        else:
            if index >= len(data):
                raise ValueError("Malformed PDF RunLength stream")
            decoded.extend(data[index : index + 1] * (257 - length))
            index += 1
        if len(decoded) > remaining:
            raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
    return bytes(decoded)
