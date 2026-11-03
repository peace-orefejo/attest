"""Small helpers for label files: write one atomically, and walk its labels."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from bench_template import LABEL_FIELDS


def write_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write `data` as a pretty-printed label file through a temporary file and os.replace, so
    a crash never leaves half a file. The temporary name starts with a dot and ends in .tmp, so
    nothing that globs `*.json` reads it."""
    text = json.dumps(data, indent=2) + "\n"
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def started(raw: dict[str, Any]) -> bool:
    """Whether anything in a label file has been filled in yet."""
    return (
        any(value is not None for value in label_values(raw.get("labels")))
        or raw.get("confidence") is not None
        or bool(str(raw.get("rationale") or "").strip())
        or raw.get("ambiguous") is True
    )


def label_values(value: object) -> list[object]:
    """Every label (claim label, verdict, recovery, run label) in a `labels` value, blank or not."""
    if isinstance(value, list):
        entries: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
        return [item for entry in entries for item in label_values(entry)]
    if not isinstance(value, dict):
        return []
    items: dict[str, Any] = value  # pyright: ignore[reportUnknownVariableType]
    return [
        found
        for key, item in items.items()
        for found in ([item] if key in LABEL_FIELDS else label_values(item))
    ]
