from __future__ import annotations

import io

from .limits import ExtractionLimits


def _image_parts(
    raw: bytes, limits: ExtractionLimits
) -> tuple[list[tuple[str, str]], list[str]]:
    from PIL import Image
    import pytesseract
    import zxingcpp
    image = Image.open(io.BytesIO(raw))
    if image.width * image.height > limits.max_image_pixels:
        raise ValueError("Image exceeds pixel limit")
    image.load()
    parts: list[tuple[str, str]] = []
    warnings: list[str] = []
    try:
        text = pytesseract.image_to_string(image, timeout=limits.ocr_timeout_seconds)
        if text.strip():
            parts.append(("image.ocr", text))
    except Exception as exc:
        warnings.append(f"OCR unavailable: {type(exc).__name__}: {exc}")
    try:
        for index, barcode in enumerate(zxingcpp.read_barcodes(image)):
            if barcode.text:
                parts.append((f"image.qr[{index}]", barcode.text))
    except Exception as exc:
        warnings.append(f"QR decoding failed: {type(exc).__name__}: {exc}")
    for key, value in image.getexif().items():
        if isinstance(value, str) and value.strip():
            parts.append((f"image.metadata[{key}]", value))
    return parts, warnings
