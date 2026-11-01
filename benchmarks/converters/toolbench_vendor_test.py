from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

import toolbench
import toolbench_vendor
from toolbench_cases import SPECS
from toolbench_test import contact_details

SOURCES = toolbench.SOURCES
ROW = re.compile(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \| `([0-9a-f]{64})` \|$", re.M)


def _source_md_rows() -> dict[str, tuple[str, str]]:
    text = (SOURCES / "SOURCE.md").read_text(encoding="utf-8")
    return {path: (upstream, vendored) for path, upstream, vendored in ROW.findall(text)}


def _vendored_files() -> set[str]:
    return {
        str(path.relative_to(SOURCES))
        for path in SOURCES.rglob("*")
        if path.is_file() and path.name not in {"SOURCE.md", "NOTICE"}
    }


def _all_strings(value: object) -> list[str]:
    """Every string in a decoded JSON value, decoding strings that hold JSON at every level."""
    if isinstance(value, str):
        try:
            inner: object = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return [value, *(_all_strings(inner) if isinstance(inner, dict | list) else [])]
    if isinstance(value, list):
        return [text for item in value for text in _all_strings(item)]
    if isinstance(value, dict):
        return [text for key, item in value.items() for text in [key, *_all_strings(item)]]
    return []


def _samples() -> list[Path]:
    return sorted(SOURCES.glob("data_example/**/*.json"))


def test_source_md_lists_every_vendored_file_with_both_digests() -> None:
    rows = _source_md_rows()
    assert set(rows) == _vendored_files() == set(toolbench_vendor.UPSTREAM)
    assert {spec.sample for spec in SPECS} <= set(rows)
    for relative, (upstream, vendored) in rows.items():
        assert upstream == toolbench_vendor.UPSTREAM[relative], relative
        assert toolbench_vendor.sha256((SOURCES / relative).read_bytes()) == vendored, relative
    assert rows["LICENSE"][0] == rows["LICENSE"][1]


def test_source_md_and_notice_name_the_pinned_commit() -> None:
    assert toolbench_vendor.COMMIT in (SOURCES / "SOURCE.md").read_text(encoding="utf-8")
    assert toolbench_vendor.COMMIT in (SOURCES / "NOTICE").read_text(encoding="utf-8")


def test_no_emails_phone_numbers_or_names_in_vendored_files() -> None:
    assert _samples()
    for path in _samples():
        raw = path.read_text(encoding="utf-8")
        assert contact_details(raw) == [], path.name
        for text in _all_strings(json.loads(raw)):
            assert contact_details(text) == [], path.name


def test_redacting_the_vendored_files_again_changes_nothing() -> None:
    for path in _samples():
        raw = path.read_bytes()
        counts: Counter[str] = Counter()
        assert toolbench_vendor.redact_json(raw, counts) == raw, path.name
        assert counts == Counter()


def test_redaction_keeps_double_encoded_json_parsing() -> None:
    inner = json.dumps({"response": json.dumps([{"email": "a.b@ex.com", "tel": "+33 12 34 56"}])})
    raw = toolbench_vendor.redact_json(json.dumps({"obs": inner}, indent=2).encode())
    level1 = json.loads(json.loads(raw)["obs"])
    level2 = json.loads(level1["response"])
    assert level2 == [{"email": "[email redacted]", "tel": "[phone redacted]"}]


def test_crlf_layout_is_kept() -> None:
    raw = json.dumps({"a": "x@y.org"}, indent=2).replace("\n", "\r\n").encode()
    assert toolbench_vendor.redact_json(raw) == b'{\r\n  "a": "[email redacted]"\r\n}'


def test_upstream_bytes_must_match_the_pinned_digest() -> None:
    with pytest.raises(ValueError, match="pinned"):
        toolbench_vendor.vendored_bytes("LICENSE", b"not the licence")


def test_a_file_that_does_not_round_trip_is_refused() -> None:
    with pytest.raises(ValueError, match="round-trip"):
        toolbench_vendor.redact_json(b'{"a":1}')
