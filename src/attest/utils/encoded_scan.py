"""Find long base64 or hex blobs and decode them, within limits, for rescanning."""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Callable, Literal

Encoding = Literal["base64", "hex"]

MIN_BLOB_CHARS = 32
MAX_DECODED_BYTES = 4_096
MIN_PRINTABLE_RATIO = 0.85
MIN_DECODED_CHARS = 8
MAX_BLOBS = 20

_HEX = re.compile(r"(?<![0-9A-Za-z])(?:0x)?([0-9a-fA-F]{%d,})(?![0-9A-Za-z])" % MIN_BLOB_CHARS)
_BASE64 = re.compile(r"(?<![A-Za-z0-9+/_-])([A-Za-z0-9+/_-]{%d,}={0,2})" % MIN_BLOB_CHARS)


@dataclass(frozen=True)
class EncodedBlob:
    encoding: Encoding
    start: int
    end: int
    decoded: str
    truncated: bool


def printable_ratio(text: str) -> float:
    """Share of characters that are printable or ordinary whitespace."""
    if not text:
        return 0.0
    good = sum(1 for ch in text if (ch.isprintable() or ch in "\n\r\t") and ch != "�")
    return good / len(text)


def _decode_hex(blob: str, max_bytes: int) -> tuple[bytes, bool] | None:
    usable = blob[: max_bytes * 2]
    usable = usable[: len(usable) - len(usable) % 2]
    try:
        return bytes.fromhex(usable), len(usable) < len(blob)
    except ValueError:
        return None


def _decode_base64(blob: str, max_bytes: int) -> tuple[bytes, bool] | None:
    body = blob.rstrip("=")
    limit = (max_bytes // 3) * 4
    usable = body[:limit]
    if len(usable) % 4 == 1:
        usable = usable[:-1]
    padded = usable + "=" * (-len(usable) % 4)
    altchars = b"-_" if ("-" in usable or "_" in usable) else None
    try:
        return base64.b64decode(padded, altchars=altchars, validate=True), len(usable) < len(body)
    except (binascii.Error, ValueError):
        return None


def _accept(raw: bytes) -> str | None:
    text = raw.decode("utf-8", errors="replace")
    if len(text.strip()) < MIN_DECODED_CHARS or printable_ratio(text) < MIN_PRINTABLE_RATIO:
        return None
    return text


_Decoder = Callable[[str, int], "tuple[bytes, bool] | None"]
_DECODERS: tuple[tuple[Encoding, re.Pattern[str], _Decoder], ...] = (
    ("hex", _HEX, _decode_hex),
    ("base64", _BASE64, _decode_base64),
)


def find_encoded(
    text: str,
    *,
    max_decoded_bytes: int = MAX_DECODED_BYTES,
    max_blobs: int = MAX_BLOBS,
) -> list[EncodedBlob]:
    """Return blobs in text that decode, within the byte limit, to mostly printable text."""
    blobs: list[EncodedBlob] = []
    taken: list[tuple[int, int]] = []
    for encoding, pattern, decode in _DECODERS:
        for match in pattern.finditer(text):
            start, end = match.span(1)
            if any(start < t_end and t_start < end for t_start, t_end in taken):
                continue
            if encoding == "hex":
                taken.append((start, end))
            decoded = decode(match.group(1), max_decoded_bytes)
            if decoded is None:
                continue
            accepted = _accept(decoded[0])
            if accepted is None:
                continue
            blobs.append(EncodedBlob(encoding, start, end, accepted, decoded[1]))
            if len(blobs) >= max_blobs:
                return sorted(blobs, key=lambda blob: blob.start)
    return sorted(blobs, key=lambda blob: blob.start)
