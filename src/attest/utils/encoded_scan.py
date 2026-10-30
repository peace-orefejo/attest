"""Find long base64 or hex blobs and decode them, within limits, for rescanning."""

from __future__ import annotations

import base64
import binascii
import bisect
import re
from collections.abc import Callable, Iterator
from typing import Literal

from pydantic import BaseModel, ConfigDict

Encoding = Literal["base64", "hex"]

MIN_BLOB_CHARS = 32
MAX_DECODED_BYTES = 4_096
MIN_PRINTABLE_RATIO = 0.85
MIN_DECODED_CHARS = 8
MAX_BLOBS = 20

_HEX = re.compile(rf"(?<![0-9A-Za-z])(?:0x)?([0-9a-fA-F]{{{MIN_BLOB_CHARS},}})(?![0-9A-Za-z])")
_BASE64 = re.compile(rf"(?<![A-Za-z0-9+/_-])([A-Za-z0-9+/_-]{{{MIN_BLOB_CHARS},}}={{0,2}})")


class EncodedBlob(BaseModel):
    """A blob of encoded text, its offsets in the source text, and its bounded decoding."""

    model_config = ConfigDict(frozen=True)

    encoding: Encoding
    start: int
    end: int
    decoded: str
    truncated: bool


class _Decoded(BaseModel):
    raw: bytes
    truncated: bool


class _Candidate(BaseModel):
    encoding: Encoding
    start: int
    end: int
    blob: str


_Decoder = Callable[[str, int], _Decoded | None]


def printable_ratio(text: str) -> float:
    """Share of characters that are printable or ordinary whitespace."""
    if not text:
        return 0.0
    good = sum(1 for ch in text if (ch.isprintable() or ch in "\n\r\t") and ch != "�")
    return good / len(text)


def find_encoded(
    text: str,
    *,
    max_decoded_bytes: int = MAX_DECODED_BYTES,
    max_blobs: int = MAX_BLOBS,
) -> list[EncodedBlob]:
    """Return blobs in text that decode, within the byte limit, to mostly printable text."""
    blobs: list[EncodedBlob] = []
    for candidate in _candidates(text):
        blob = _decode_candidate(candidate, max_decoded_bytes)
        if blob is None:
            continue
        blobs.append(blob)
        if len(blobs) >= max_blobs:
            break
    return sorted(blobs, key=lambda blob: blob.start)


def _candidates(text: str) -> Iterator[_Candidate]:
    hex_starts: list[int] = []
    hex_ends: list[int] = []
    for match in _HEX.finditer(text):
        start, end = match.span(1)
        hex_starts.append(start)
        hex_ends.append(end)
        yield _Candidate(encoding="hex", start=start, end=end, blob=match.group(1))
    for match in _BASE64.finditer(text):
        start, end = match.span(1)
        if _overlaps(hex_starts, hex_ends, start, end):
            continue
        yield _Candidate(encoding="base64", start=start, end=end, blob=match.group(1))


def _overlaps(starts: list[int], ends: list[int], start: int, end: int) -> bool:
    index = bisect.bisect_left(starts, end) - 1
    return index >= 0 and ends[index] > start


def _decode_candidate(candidate: _Candidate, max_bytes: int) -> EncodedBlob | None:
    decoder = _DECODERS[candidate.encoding]
    decoded = decoder(candidate.blob, max_bytes)
    if decoded is None:
        return None
    accepted = _accept(decoded.raw)
    if accepted is None:
        return None
    return EncodedBlob(
        encoding=candidate.encoding,
        start=candidate.start,
        end=candidate.end,
        decoded=accepted,
        truncated=decoded.truncated,
    )


def _decode_hex(blob: str, max_bytes: int) -> _Decoded | None:
    usable = blob[: max_bytes * 2]
    usable = usable[: len(usable) - len(usable) % 2]
    try:
        return _Decoded(raw=bytes.fromhex(usable), truncated=len(usable) < len(blob))
    except ValueError:
        return None


def _decode_base64(blob: str, max_bytes: int) -> _Decoded | None:
    body = blob.rstrip("=")
    usable = body[: (max_bytes // 3) * 4]
    if len(usable) % 4 == 1:
        usable = usable[:-1]
    padded = usable + "=" * (-len(usable) % 4)
    altchars = b"-_" if ("-" in usable or "_" in usable) else None
    try:
        raw = base64.b64decode(padded, altchars=altchars, validate=True)
    except (binascii.Error, ValueError):
        return None
    return _Decoded(raw=raw, truncated=len(usable) < len(body))


def _accept(raw: bytes) -> str | None:
    text = raw.decode("utf-8", errors="replace")
    if len(text.strip()) < MIN_DECODED_CHARS or printable_ratio(text) < MIN_PRINTABLE_RATIO:
        return None
    return text


_DECODERS: dict[Encoding, _Decoder] = {"hex": _decode_hex, "base64": _decode_base64}
