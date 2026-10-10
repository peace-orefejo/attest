"""Decoded-size accounting over the PDF streams that pypdf text extraction reads."""

from __future__ import annotations

from .pdf_decode import bounded_pdf_decode


def check_pdf_page_budget(page, used: int, limit: int, seen: set[int]) -> int:
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
    decoded_size = len(bounded_pdf_decode(resolved, remaining, limit))
    return used + decoded_size
