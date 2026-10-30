from __future__ import annotations

import io
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from .limits import ExtractionLimits
from .parts import ExtractedPart, ParsedParts
from .pdf_budget import PdfDecodeBudget

if TYPE_CHECKING:
    from pypdf import PageObject


def pdf_parts(raw: bytes, limits: ExtractionLimits) -> ParsedParts:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw), strict=False)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF cannot be inspected")
    pages = reader.pages
    return ParsedParts(
        parts=_page_texts(pages[: limits.max_pdf_pages], limits.max_pdf_decoded_bytes),
        truncated=len(pages) > limits.max_pdf_pages,
    )


def _page_texts(pages: Sequence[PageObject], decoded_limit: int) -> Iterator[ExtractedPart]:
    budget = PdfDecodeBudget(decoded_limit)
    for index, page in enumerate(pages):
        budget.charge_page(page)
        text = page.extract_text() or ""
        if text.strip():
            yield ExtractedPart(source_kind=f"pdf.page[{index + 1}]", text=text)
