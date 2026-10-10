"""PDF page text, extracted only after each page's decoded streams fit the budget."""

from __future__ import annotations

import io
from typing import Iterable

from ..limits import ExtractionLimits
from .pdf_budget import check_pdf_page_budget


def pdf_parts(
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
            decoded_used = check_pdf_page_budget(
                page, decoded_used, limits.max_pdf_decoded_bytes, seen_streams
            )
            text = page.extract_text() or ""
            if text.strip():
                yield (f"pdf.page[{index + 1}]", text)
    return parts(), truncated
