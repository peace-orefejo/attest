"""Tests for the AgentDojo converter and the cases it writes."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

import agentdojo
from bench_cases import SEED_ORIGIN, Case
from bench_load import load_datasets

LABEL_FIELDS = {"utility", "security", "duration"}


def _committed_cases() -> list[tuple[str, dict[str, object]]]:
    found: list[tuple[str, dict[str, object]]] = []
    for path in sorted(agentdojo.DATASETS_DIR.glob(f"*/*-{agentdojo.ORIGIN}.jsonl")):
        split = path.name.removesuffix(f"-{agentdojo.ORIGIN}.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines():
            found.append((split, json.loads(line)))
    return found


def test_regeneration_is_byte_identical(tmp_path: Path) -> None:
    written = agentdojo.write_cases(datasets=tmp_path)
    assert written, "the converter wrote no case files"
    committed = sorted(agentdojo.DATASETS_DIR.glob(f"*/*-{agentdojo.ORIGIN}.jsonl"))
    assert sorted(p.relative_to(tmp_path) for p in written) == [
        p.relative_to(agentdojo.DATASETS_DIR) for p in committed
    ]
    for path in written:
        committed_path = agentdojo.DATASETS_DIR / path.relative_to(tmp_path)
        assert path.read_bytes() == committed_path.read_bytes(), path
    again = tmp_path / "again"
    for path in agentdojo.write_cases(datasets=again):
        assert path.read_bytes() == (tmp_path / path.relative_to(again)).read_bytes()


def test_every_case_validates() -> None:
    cases = _committed_cases()
    assert len(cases) == len(agentdojo.SELECTIONS)
    for split, case in cases:
        model = Case.model_validate(case)
        assert model.source == "community"
        assert model.label_status == "draft"
        assert model.annotators == []
        assert model.notes.startswith("DRAFT label by the converter author;")
        assert model.origin == agentdojo.ORIGIN
        assert model.origin_ref is not None
        assert (agentdojo.SOURCE_DIR / model.origin_ref).is_file()
        assert split in {"dev", "validation", "heldout"}


def test_public_loader_reads_every_case() -> None:
    every = [
        (split, case)
        for by_split in load_datasets().cases.values()
        for split, cases in by_split.items()
        for case in cases
    ]
    ours = {case.id: split for split, case in every if case.origin == agentdojo.ORIGIN}
    assert ours == {str(case["id"]): split for split, case in _committed_cases()}
    families = {case.task_family for _, case in every if case.origin == agentdojo.ORIGIN}
    others = {case.task_family for _, case in every if case.origin != agentdojo.ORIGIN}
    assert not families & others
    assert not any(family.startswith(f"{SEED_ORIGIN}/") for family in families)


def test_tool_use_notes_say_incorrect_needs_appropriate() -> None:
    for _, case in _committed_cases():
        if case["check"] == "tool_use":
            assert "--appropriate" in str(case["notes"]), case["id"]


def test_ids_are_unique_and_prefixed() -> None:
    ids = [str(case["id"]) for _, case in _committed_cases()]
    assert len(ids) == len(set(ids))
    assert all(case_id.startswith(f"{agentdojo.ORIGIN}-") for case_id in ids)


def test_suites_map_to_one_split_each() -> None:
    assert agentdojo.SPLIT_BY_SUITE == {
        "banking": "dev",
        "slack": "dev",
        "travel": "validation",
        "workspace": "heldout",
    }
    family_splits: dict[str, set[str]] = {}
    for split, case in _committed_cases():
        family = str(case["task_family"])
        suite = family.removeprefix(f"{agentdojo.ORIGIN}/")
        assert family == f"{agentdojo.ORIGIN}/{suite}"
        assert split == agentdojo.SPLIT_BY_SUITE[suite]
        family_splits.setdefault(family, set()).add(split)
    assert all(len(splits) == 1 for splits in family_splits.values())
    assert set(family_splits) == {f"agentdojo/{s}" for s in agentdojo.SPLIT_BY_SUITE}


def test_label_mix() -> None:
    labels = [
        case["expected"]["label"]  # type: ignore[index]
        for _, case in _committed_cases()
        if case["check"] == "prompt_injection"
    ]
    assert labels.count("none") >= 2
    assert {"none", "payload", "compromised"} <= set(labels)
    assert any(case["check"] == "tool_use" for _, case in _committed_cases())


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for key, item in value.items():  # type: ignore[reportUnknownVariableType]
            found.add(str(key))  # type: ignore[reportUnknownArgumentType]
            found |= _keys(item)
        return found
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value))  # type: ignore[reportUnknownVariableType]
    return set()


def test_no_evaluation_fields_leak() -> None:
    for _, case in _committed_cases():
        assert not _keys(case) & LABEL_FIELDS, case["id"]
        assert "injections" not in _keys(case)
    for path in (agentdojo.SOURCE_DIR / "runs").rglob("*.json"):
        run = json.loads(path.read_text(encoding="utf-8"))
        assert set(run) <= set(agentdojo.KEPT_RUN_FIELDS), path
        assert not set(run) & LABEL_FIELDS, path


def test_strip_run_drops_grading() -> None:
    run = {"suite_name": "banking", "messages": [], "utility": True, "security": False}
    assert agentdojo.strip_run(run) == {"suite_name": "banking", "messages": []}


def _source_table() -> dict[str, str]:
    text = (agentdojo.SOURCE_DIR / "SOURCE.md").read_text(encoding="utf-8")
    rows = re.findall(
        r"^\| `([^`]+)` \| `[^`]+` \| `[0-9a-f]{64}` \| `([0-9a-f]{64})` \|$", text, re.M
    )
    return dict(rows)


def test_vendored_hashes_match_source_md() -> None:
    table = _source_table()
    vendored = {
        str(path.relative_to(agentdojo.SOURCE_DIR))
        for path in agentdojo.SOURCE_DIR.rglob("*")
        if path.is_file() and path.name not in {"SOURCE.md", "NOTICE"}
    }
    assert set(table) == vendored
    for rel, digest in table.items():
        assert hashlib.sha256((agentdojo.SOURCE_DIR / rel).read_bytes()).hexdigest() == digest, rel


def test_source_md_pins_the_commit() -> None:
    text = (agentdojo.SOURCE_DIR / "SOURCE.md").read_text(encoding="utf-8")
    assert agentdojo.UPSTREAM_COMMIT in text
    assert (agentdojo.SOURCE_DIR / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")


def test_vendored_size_is_small() -> None:
    total = sum(p.stat().st_size for p in agentdojo.SOURCE_DIR.rglob("*") if p.is_file())
    assert total < 1_000_000


def test_allowed_tools_come_from_the_suite() -> None:
    assert agentdojo.suite_tools("banking")[:2] == ["get_iban", "send_money"]
    for _, case in _committed_cases():
        traj = case["trajectory"]
        suite = str(case["task_family"]).split("/")[1]
        assert traj["allowed_tools"] == agentdojo.suite_tools(suite)  # type: ignore[index]
        for step in traj["steps"]:  # type: ignore[index]
            assert step["tool_call"]["name"] in traj["allowed_tools"]  # type: ignore[index]


def test_error_calls_are_marked() -> None:
    selection = next(s for s in agentdojo.SELECTIONS if s.suite == "workspace" and s.user_task == 2)
    case = agentdojo.build_case(selection)
    steps = case["trajectory"]["steps"]  # type: ignore[index]
    assert steps[1]["tool_call"]["is_error"] is True  # type: ignore[index]
    assert steps[1]["tool_call"]["output"].startswith("ValueError")  # type: ignore[index]
    assert all("is_error" not in s["tool_call"] for i, s in enumerate(steps) if i != 1)  # type: ignore[index]


def test_off_task_step_must_match_tool_name() -> None:
    selection = next(s for s in agentdojo.SELECTIONS if s.check == "tool_use")
    wrong = selection.model_copy(update={"off_task_calls": {0: "send_money_not_here"}})
    with pytest.raises(ValueError, match="step 0"):
        agentdojo.build_case(wrong)
