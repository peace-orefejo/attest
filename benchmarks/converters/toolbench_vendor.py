"""Vendor the ToolBench inputs: fetch them at the pinned commit, check them, redact them.

Run `uv run python benchmarks/converters/toolbench.py --vendor` (needs network access to
raw.githubusercontent.com). Each upstream file must match the sha256 recorded in `UPSTREAM`.
`LICENSE` is copied verbatim; each JSON sample is decoded, every string in it (keys included) is
redacted with `toolbench_redact.redact`, and it is written back in upstream's own layout
(two-space indent, ASCII escapes, upstream's line endings), so only redacted spans change.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from collections import Counter
from pathlib import Path
from typing import cast

from toolbench_redact import redact_value

COMMIT = "d56fdd89faf8c91fa135090b212bb9057ee5cfc2"
RAW_URL = f"https://raw.githubusercontent.com/OpenBMB/ToolBench/{COMMIT}/{{}}"
_SAMPLE = "data_example/answer/{}_answer/{}_ChatGPT_DFS_woFilter_w2.json"
# sha256 of each file as published upstream at COMMIT.
UPSTREAM = {
    _SAMPLE.format("G1", 10): "76a77721640045e07142c669008611e6b82b25007c73427aec771adbf9dd9841",
    _SAMPLE.format("G1", 11): "3f935fe99b99beccb727763e8407ab9fdb5f2cf45d85d998327b669ab2ea52ab",
    _SAMPLE.format("G1", 57): "8279c9999dad881db8bc9e112feeb51ca2861e89d835111408f218af297af531",
    _SAMPLE.format("G1", 59): "8fea509e1be896331fdfd587ab4668281ee820f89cdb9a1760c218ed7804c2be",
    _SAMPLE.format("G2", 52): "c6c2da0b425e0122838b1e15be199492686b2b10b1d60605d6a52523c214bdcb",
    _SAMPLE.format("G2", 127): "a32cc5c8947b2db443fd0c6c9a3b12905624c15a460ec7e9d4fa18df345675e8",
    _SAMPLE.format("G3", 21): "5f99a71cae2979600262f7b6b9b475399530496b56f475b03727b27b0cdfb176",
    _SAMPLE.format("G3", 3): "fdf868ff795bc0c9a153f4d492f40eb889caa2f60cad931bca6209c2e11dc263",
    "LICENSE": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dump(value: object, newline: str) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True).replace("\n", newline)


def _decode(text: str) -> tuple[bool, object]:
    try:
        return True, json.loads(text)
    except json.JSONDecodeError:
        return False, None


def check_nested(original: object, redacted: object) -> None:
    """Every string that held JSON upstream still holds JSON after redaction, and decoding it
    gives the same as redacting the decoded original (checked at every nesting level)."""
    if isinstance(original, str):
        was_json, decoded = _decode(original)
        if not was_json or not isinstance(decoded, dict | list):
            return
        inner = cast(object, decoded)
        still_json, inner_redacted = _decode(cast(str, redacted))
        if not still_json or inner_redacted != redact_value(inner):
            raise ValueError(f"redaction broke a JSON string: {original[:80]!r}")
        check_nested(inner, inner_redacted)
    elif isinstance(original, list):
        items, others = cast(list[object], original), cast(list[object], redacted)
        for item, other in zip(items, others, strict=True):
            check_nested(item, other)
    elif isinstance(original, dict):
        values = cast(dict[str, object], original).values()
        others = cast(dict[str, object], redacted).values()
        for item, other in zip(values, others, strict=True):
            check_nested(item, other)


def redact_json(raw: bytes, counts: Counter[str] | None = None) -> bytes:
    """Redact one JSON sample, keeping it valid JSON in upstream's own layout."""
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    data: object = json.loads(text)
    if _dump(data, newline) != text:
        raise ValueError("sample does not round-trip through json; refusing to rewrite it")
    redacted = redact_value(data, counts)
    check_nested(data, redacted)
    return _dump(redacted, newline).encode("utf-8")


def vendored_bytes(relative: str, upstream: bytes, counts: Counter[str] | None = None) -> bytes:
    if sha256(upstream) != UPSTREAM[relative]:
        raise ValueError(f"{relative}: upstream sha256 {sha256(upstream)} is not the pinned one")
    return redact_json(upstream, counts) if relative.endswith(".json") else upstream


def fetch(relative: str) -> bytes:
    with urllib.request.urlopen(RAW_URL.format(relative), timeout=60) as response:
        return cast(bytes, response.read())


def vendor(sources: Path) -> None:
    for relative in UPSTREAM:
        counts: Counter[str] = Counter()
        data = vendored_bytes(relative, fetch(relative), counts)
        target = sources / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        found = ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items())) or "nothing"
        print(f"vendored {relative} (sha256 {sha256(data)}; redacted {found})")
