from __future__ import annotations

from dataclasses import dataclass

from ..content import TextSegment


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
            "max_bytes",
            "max_chars",
            "max_scan_chars",
            "max_scan_segments",
            "max_artifacts",
            "max_detections",
            "max_pdf_pages",
            "max_pdf_decoded_bytes",
            "max_image_pixels",
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
