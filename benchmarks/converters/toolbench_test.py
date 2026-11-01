from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest

import toolbench
import toolbench_redact
from bench_cases import SEED_ORIGIN, Case
from bench_load import load_datasets

ORIGIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
FAMILY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_./-]*$")
LABEL_LIKE_KEYS = {
    "win",
    "reward",
    "Elo",
    "valid_data",
    "finish_type",
    "compare_candidates",
    "mento-carlo-action-value",
    "query_count",
    "total_tokens",
    "pruned",
    "is_terminal",
}
EMAIL = re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")
PHONES = (
    re.compile(r"\+\s?\d[\d\s.()-]{5,}\d"),
    re.compile(r"(?<![\d.])\d{2,4}[ .]\d{2}[ .]\d{2}(?![\d.])"),
    re.compile(r"\(\d{3}\)\s?\d{3}-\d{4}"),
)


def contact_details(text: str) -> list[str]:
    """Every email, phone number or listed name the checks find in `text`."""
    found = [match.group() for pattern in (EMAIL, *PHONES) for match in pattern.finditer(text)]
    words = toolbench_redact.WORD.findall(text)
    return found + [word for word in words if toolbench_redact.is_listed_name(word)]


def _emitted() -> list[tuple[Path, dict[str, object]]]:
    files = sorted(toolbench.DATASETS.glob(f"*/*-{toolbench.ORIGIN}.jsonl"))
    return [(path, json.loads(line)) for path in files for line in path.read_text().splitlines()]


def _split_of(path: Path) -> str:
    return path.name.removesuffix(f"-{toolbench.ORIGIN}.jsonl")


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(k) for k in value} | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for item in value for k in _keys(item)}
    return set()


def test_files_on_disk_match_a_fresh_conversion() -> None:
    built = toolbench.build_all()
    assert {path for path, _ in _emitted()} == set(built)
    for path, cases in built.items():
        assert path.read_text(encoding="utf-8") == toolbench.render(cases)


def test_conversion_is_deterministic() -> None:
    first = {p: toolbench.render(c) for p, c in toolbench.build_all().items()}
    second = {p: toolbench.render(c) for p, c in toolbench.build_all().items()}
    assert first == second


def test_every_case_validates_against_the_case_model() -> None:
    for _, case in _emitted():
        Case.model_validate(case)


def test_public_datasets_load_with_every_toolbench_case() -> None:
    loaded = [
        (split, case)
        for splits in load_datasets().cases.values()
        for split, cases in splits.items()
        for case in cases
    ]
    ours = {case.id: split for split, case in loaded if case.origin == toolbench.ORIGIN}
    assert ours == {str(case["id"]): _split_of(path) for path, case in _emitted()}
    others = {case.task_family for _, case in loaded if case.origin != toolbench.ORIGIN}
    assert not others & {f"toolbench/g{n}" for n in (1, 2, 3)}
    assert all(
        not case.task_family.startswith("toolbench/")
        for _, case in loaded
        if case.origin == SEED_ORIGIN
    )


def test_new_fields_follow_the_contract() -> None:
    cases = [case for _, case in _emitted()]
    ids = [str(case["id"]) for case in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        assert str(case["id"]).startswith("toolbench-")
        assert case["origin"] == "toolbench"
        assert ORIGIN_PATTERN.match(str(case["origin"]))
        assert FAMILY_PATTERN.match(str(case["task_family"]))
        assert isinstance(case["origin_ref"], str)
        assert (toolbench.SOURCES / case["origin_ref"].split("#")[0]).is_file()
        assert case["source"] == "community"
        assert case["label_status"] == "draft"
        assert case["annotators"] == []
        assert str(case["notes"]).startswith("DRAFT label by the converter author;")


def test_groups_map_to_splits_and_each_family_to_one_split() -> None:
    splits_by_family: dict[str, set[str]] = {}
    for path, case in _emitted():
        group = re.search(r"G(\d)_answer", str(case["origin_ref"]))
        assert group is not None
        expected = {"1": "dev", "2": "validation", "3": "heldout"}[group.group(1)]
        assert _split_of(path) == expected
        assert case["task_family"] == f"toolbench/g{group.group(1)}"
        splits_by_family.setdefault(str(case["task_family"]), set()).add(_split_of(path))
    assert all(len(splits) == 1 for splits in splits_by_family.values())


def test_no_rapidapi_tool_is_offered_in_two_splits() -> None:
    splits_by_tool: dict[str, set[str]] = {}
    for path, case in _emitted():
        trajectory = case["trajectory"]
        assert isinstance(trajectory, dict)
        for name in trajectory["allowed_tools"]:
            tool = name.rsplit("_for_", 1)[-1]
            splits_by_tool.setdefault(tool, set()).add(_split_of(path))
    shared = {tool: splits for tool, splits in splits_by_tool.items() if len(splits) > 1}
    assert shared == {}


def test_no_reward_or_search_tree_fields_leak() -> None:
    for _, case in _emitted():
        assert not _keys(case) & LABEL_LIKE_KEYS
        text = json.dumps(case)
        assert "mento-carlo" not in text
        assert "This is not the first time you try this task" not in text


def test_no_emails_or_phone_numbers_in_emitted_cases() -> None:
    for _, case in _emitted():
        assert contact_details(json.dumps(case, ensure_ascii=False)) == [], case["id"]


def test_truncated_observation_keeps_the_marker() -> None:
    content = '{"error": "", "response": "[{\\"id\\":\\"EKVF\\",\\"name\\":\\"EK...'
    observation = toolbench.parse_observation(content)
    assert observation.truncated
    assert toolbench.render_output(observation) == '[{"id":"EKVF","name":"EK...'


def test_error_field_marks_the_call_as_an_error() -> None:
    observation = toolbench.parse_observation('{"error": "Timeout", "response": ""}')
    assert toolbench.render_output(observation) == "error: Timeout\nresponse: "


def test_chain_must_end_with_finish() -> None:
    sample = toolbench.AnswerGeneration(
        query="q",
        function=[],
        train_messages=[[toolbench.Message(role="user", content="q")]],
    )
    with pytest.raises(ValueError, match="Finish"):
        toolbench.select_chain(sample)


def test_redaction_covers_contact_details() -> None:
    text = "Mail j.doe@example.com or call +33 12.34.56.78."
    assert toolbench_redact.redact(text) == "Mail [email redacted] or call [phone redacted]."


def test_listed_names_are_matched_by_hash_as_whole_words(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = hashlib.sha256(b"doe").hexdigest()
    monkeypatch.setattr(toolbench_redact, "NAME_SHA256", frozenset({digest}))
    counts: Counter[str] = Counter()
    redacted = toolbench_redact.redact("Ask Ms DOE (doe) or Doering at j.doe@example.com.", counts)
    assert redacted == "Ask Ms [name redacted] ([name redacted]) or Doering at [email redacted]."
    assert counts == Counter(name=2, email=1)
