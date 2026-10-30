from __future__ import annotations

import base64
from pathlib import Path

from ..content import Artifact


def read_artifact_bytes(artifact: Artifact, max_bytes: int, allow_paths: bool) -> bytes:
    if artifact.data_base64 is not None:
        raw = _decode_base64(artifact.data_base64, max_bytes)
    elif artifact.path is not None:
        raw = _read_path(artifact.path, max_bytes, allow_paths)
    else:
        raise ValueError("Artifact has no readable content")
    _require_within(len(raw), max_bytes)
    return raw


def _decode_base64(encoded: str, max_bytes: int) -> bytes:
    _require_within(_estimated_decoded_size(encoded), max_bytes)
    return base64.b64decode(encoded, validate=True)


def _estimated_decoded_size(encoded: str) -> int:
    padding = 2 if encoded.endswith("==") else (1 if encoded.endswith("=") else 0)
    return len(encoded) * 3 // 4 - padding


def _read_path(raw_path: str, max_bytes: int, allow_paths: bool) -> bytes:
    if not allow_paths:
        raise ValueError("Path extraction is disabled; pass allow_paths=True explicitly")
    path = Path(raw_path)
    _require_within(path.stat().st_size, max_bytes)
    return path.read_bytes()


def _require_within(size: int, max_bytes: int) -> None:
    if size > max_bytes:
        raise ValueError(f"Artifact exceeds {max_bytes} byte limit")
