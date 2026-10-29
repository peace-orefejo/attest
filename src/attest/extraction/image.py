from __future__ import annotations

import io
from typing import TYPE_CHECKING

from ..utils.imports import load_callable
from .limits import ExtractionLimits
from .parts import ExtractedPart, ParsedParts

if TYPE_CHECKING:
    from PIL.Image import Image


def image_parts(raw: bytes, limits: ExtractionLimits) -> ParsedParts:
    image = _load_bounded_image(raw, limits.max_image_pixels)
    ocr = _ocr_parts(image, limits.ocr_timeout_seconds)
    barcodes = _barcode_parts(image)
    metadata = _exif_parts(image)
    return ParsedParts(
        parts=[*ocr.parts, *barcodes.parts, *metadata],
        warnings=[*ocr.warnings, *barcodes.warnings],
    )


def _load_bounded_image(raw: bytes, max_pixels: int) -> Image:
    from PIL import Image

    image = Image.open(io.BytesIO(raw))
    if image.width * image.height > max_pixels:
        raise ValueError("Image exceeds pixel limit")
    image.load()
    return image


def _ocr_parts(image: Image, timeout_seconds: int) -> ParsedParts:
    try:
        text = _ocr_text(image, timeout_seconds)
    except Exception as exc:
        return ParsedParts(parts=[], warnings=[f"OCR unavailable: {type(exc).__name__}: {exc}"])
    if not text.strip():
        return ParsedParts(parts=[])
    return ParsedParts(parts=[ExtractedPart(source_kind="image.ocr", text=text)])


def _ocr_text(image: Image, timeout_seconds: int) -> str:
    image_to_string = load_callable("pytesseract", "image_to_string")
    text = image_to_string(image, timeout=timeout_seconds)
    if not isinstance(text, str):
        raise TypeError(f"OCR returned {type(text).__name__}, expected str")
    return text


def _barcode_parts(image: Image) -> ParsedParts:
    import zxingcpp

    try:
        parts = [
            ExtractedPart(source_kind=f"image.qr[{index}]", text=barcode.text)
            for index, barcode in enumerate(zxingcpp.read_barcodes(image))
            if barcode.text
        ]
    except Exception as exc:
        return ParsedParts(parts=[], warnings=[f"QR decoding failed: {type(exc).__name__}: {exc}"])
    return ParsedParts(parts=parts)


def _exif_parts(image: Image) -> list[ExtractedPart]:
    return [
        ExtractedPart(source_kind=f"image.metadata[{key}]", text=value)
        for key, value in image.getexif().items()
        if isinstance(value, str) and value.strip()
    ]
