from __future__ import annotations

import pytest

from bench_layout import CaseFileName, parse_case_file_name


@pytest.mark.parametrize(
    ("name", "parsed"),
    [
        ("dev.jsonl", CaseFileName(split="dev")),
        ("validation.jsonl", CaseFileName(split="validation")),
        ("heldout-tau-bench.jsonl", CaseFileName(split="heldout", origin="tau-bench")),
        ("dev-tool_bench2.jsonl", CaseFileName(split="dev", origin="tool_bench2")),
    ],
)
def test_case_file_names_parse(name: str, parsed: CaseFileName) -> None:
    assert parse_case_file_name(name) == parsed


@pytest.mark.parametrize(
    "name",
    [
        "dev.JSONL",
        "Dev.jsonl",
        "dev.json",
        "dev-Tau.jsonl",
        "dev_tau.jsonl",
        "valid.jsonl",
        "dev-.jsonl",
        "heldout-dev.jsonl",
        "dev-validation.jsonl",
        "README.md",
    ],
)
def test_other_names_are_not_case_files(name: str) -> None:
    assert parse_case_file_name(name) is None
