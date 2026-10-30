from __future__ import annotations

from pathlib import Path

_SUFFIX_MEDIA_TYPES = {
    ".json": "application/json",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".xml": "application/xml",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def guess_media_type(name: str | None) -> str:
    """Map a file name's suffix to a media type, defaulting to application/octet-stream."""
    suffix = Path(name or "").suffix.lower()
    return _SUFFIX_MEDIA_TYPES.get(suffix, "application/octet-stream")


def sniff_media_type(raw: bytes) -> str | None:
    """Recognize bounded binary signatures before trusting caller-supplied media types."""
    if raw.startswith(b"%PDF-"):
        return "application/pdf"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    return None
