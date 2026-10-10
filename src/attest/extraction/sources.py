"""Size-bounded reading of artifact bytes from inline base64 or an allowed path."""

from __future__ import annotations

import base64
from pathlib import Path

from ..core import Artifact
from .limits import ExtractionLimits


def read_bytes(artifact: Artifact, limits: ExtractionLimits, allow_paths: bool) -> bytes:
    if artifact.data_base64 is not None:
        padding = 2 if artifact.data_base64.endswith("==") else (
            1 if artifact.data_base64.endswith("=") else 0
        )
        estimated = len(artifact.data_base64) * 3 // 4 - padding
        if estimated > limits.max_bytes:
            raise ValueError(f"Artifact exceeds {limits.max_bytes} byte limit")
        raw = base64.b64decode(artifact.data_base64, validate=True)
    elif artifact.path is not None:
        if not allow_paths:
            raise ValueError("Path extraction is disabled; pass allow_paths=True explicitly")
        path = Path(artifact.path)
        if path.stat().st_size > limits.max_bytes:
            raise ValueError(f"Artifact exceeds {limits.max_bytes} byte limit")
        raw = path.read_bytes()
    else:
        raise ValueError("Artifact has no readable content")
    if len(raw) > limits.max_bytes:
        raise ValueError(f"Artifact exceeds {limits.max_bytes} byte limit")
    return raw
