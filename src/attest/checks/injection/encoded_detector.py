from __future__ import annotations

from ...content import Detection, TextSegment
from ...utils.encoded_scan import MAX_BLOBS, MAX_DECODED_BYTES, EncodedBlob, find_encoded
from ...utils.json_types import JsonObject
from .detectors import POSSIBLE_INJECTION_THRESHOLD, InjectionDetector, RegexDetector
from .hidden_unicode import first_bidi, reveal

BIDI_CONFIDENCE = 1.0


class EncodedPayloadDetector:
    """Decode bounded base64 and hex blobs and report only payload-shaped decoded text."""

    name = "encoded"

    def __init__(
        self,
        decoded_detector: InjectionDetector | None = None,
        *,
        max_decoded_bytes: int = MAX_DECODED_BYTES,
        max_blobs: int = MAX_BLOBS,
    ) -> None:
        if max_decoded_bytes <= 0 or max_blobs <= 0:
            raise ValueError("max_decoded_bytes and max_blobs must be positive.")
        self._inner = decoded_detector if decoded_detector is not None else RegexDetector()
        self._max_decoded_bytes = max_decoded_bytes
        self._max_blobs = max_blobs

    def scan(self, segment: TextSegment) -> list[Detection]:
        detections: list[Detection] = []
        blobs = find_encoded(
            segment.text, max_decoded_bytes=self._max_decoded_bytes, max_blobs=self._max_blobs
        )
        for blob in blobs:
            decoded = segment.model_copy(update={"text": blob.decoded, "metadata": {}})
            detections.extend(
                self._rewrap(segment, blob, inner) for inner in self._inner.scan(decoded)
            )
            bidi_at = first_bidi(blob.decoded)
            if bidi_at is not None:
                detections.append(self._bidi(segment, blob, bidi_at))
        return detections

    def _rewrap(self, segment: TextSegment, blob: EncodedBlob, inner: Detection) -> Detection:
        metadata: JsonObject = dict(inner.metadata)
        decoded_start = metadata.pop("char_start", None)
        decoded_end = metadata.pop("char_end", None)
        if decoded_start is not None:
            metadata["decoded_start"] = decoded_start
            metadata["decoded_end"] = decoded_end
        return inner.model_copy(
            update={
                "detector": self.name,
                "metadata": {**segment.metadata, **metadata, **_blob_metadata(blob)},
            }
        )

    def _bidi(self, segment: TextSegment, blob: EncodedBlob, offset: int) -> Detection:
        excerpt = blob.decoded[max(0, offset - 15) : offset + 45]
        confidence = BIDI_CONFIDENCE * segment.extraction_confidence
        return Detection(
            verdict="possible_injection"
            if confidence < POSSIBLE_INJECTION_THRESHOLD
            else "suspicious",
            detector=self.name,
            category="hidden_unicode",
            matched_text=reveal(excerpt).strip(),
            location=segment.location,
            subject=segment.subject,
            step=segment.step,
            confidence=confidence,
            metadata={
                **segment.metadata,
                "pattern": "bidi_control",
                "decoded_start": offset,
                "decoded_end": offset + 1,
                **_blob_metadata(blob),
            },
        )


def _blob_metadata(blob: EncodedBlob) -> JsonObject:
    return {
        "encoding": blob.encoding,
        "char_start": blob.start,
        "char_end": blob.end,
        "decoded_truncated": blob.truncated,
    }
