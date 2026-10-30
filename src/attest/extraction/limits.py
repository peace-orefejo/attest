from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from ..content import TextSegment


class ExtractionLimits(BaseModel):
    """Byte, character, page, pixel, and time budgets applied to untrusted artifacts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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

    @field_validator("*", mode="before")
    @classmethod
    def _require_positive_integer(cls, value: object, info: ValidationInfo) -> object:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{info.field_name} must be a positive integer")
        return value


class ExtractionOutcome(BaseModel):
    """Segments extracted from one artifact, plus any warning and truncation state."""

    segments: list[TextSegment]
    warning: str | None = None
    truncated: bool = False
    inspected: bool = False

    def __init__(
        self,
        segments: list[TextSegment],
        warning: str | None = None,
        truncated: bool = False,
        inspected: bool = False,
    ) -> None:
        super().__init__(
            segments=segments, warning=warning, truncated=truncated, inspected=inspected
        )
