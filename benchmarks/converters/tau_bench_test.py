from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from bench_cases import Case

# isort: split
from tau_bench import (
    DATASETS_DIR,
    ORIGIN,
    SOURCE_DIR,
    SPLIT_OF_FAMILY,
    TOOLS,
    case_files,
    domain_of,
    load_runs,
    task_family,
    write_cases,
)
from tau_bench_selection import CASES

NEW_FIELDS = {"origin", "task_family", "origin_ref"}
LABEL_KEYS = {"reward", "reward_info", "info", "actions", "outputs", "success", "user_cost"}
FILE_NAME = re.compile(rf"^(dev|validation|heldout)-{re.escape(ORIGIN)}\.jsonl$")


def _emitted() -> list[tuple[str, dict[str, object]]]:
    cases: list[tuple[str, dict[str, object]]] = []
    for path in sorted(DATASETS_DIR.glob(f"*/*-{ORIGIN}.jsonl")):
        match = FILE_NAME.match(path.name)
        assert match, path
        for line in path.read_text(encoding="utf-8").splitlines():
            cases.append((match.group(1), json.loads(line)))
    return cases


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        items: dict[str, object] = {str(k): v for k, v in value.items()}
        return set(items).union(*(_keys(v) for v in items.values()))
    if isinstance(value, list):
        return set[str]().union(*(_keys(v) for v in value))
    return set()


def test_regenerating_gives_byte_identical_files(tmp_path: Path) -> None:
    first = case_files()
    assert first == case_files()
    write_cases(tmp_path)
    committed = {
        str(path.relative_to(DATASETS_DIR)): path.read_bytes()
        for path in DATASETS_DIR.glob(f"*/*-{ORIGIN}.jsonl")
    }
    regenerated = {
        str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.glob("*/*.jsonl")
    }
    assert regenerated == committed


def test_every_case_validates_and_carries_the_new_fields() -> None:
    cases = _emitted()
    assert len(cases) == len(CASES)
    for _, case in cases:
        Case.model_validate({k: v for k, v in case.items() if k not in NEW_FIELDS})
        assert re.fullmatch(r"[a-z0-9][a-z0-9_-]*", str(case["origin"]))
        assert re.fullmatch(r"[a-z0-9][a-z0-9_./-]*", str(case["task_family"]))
        assert case["origin"] == ORIGIN
        assert case["source"] == "community"
        assert case["label_status"] == "draft"
        assert case["annotators"] == []
        assert str(case["notes"]).startswith("DRAFT label by the converter author;")
    ids = [str(case["id"]) for _, case in cases]
    assert len(set(ids)) == len(ids)
    assert all(case_id.startswith(f"{ORIGIN}-") for case_id in ids)


def test_cases_sit_in_their_check_folder() -> None:
    for path in DATASETS_DIR.glob(f"*/*-{ORIGIN}.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            assert json.loads(line)["check"] == path.parent.name


def test_splits_follow_the_task_family_rule() -> None:
    family_splits: dict[str, set[str]] = {}
    for split, case in _emitted():
        family_splits.setdefault(str(case["task_family"]), set()).add(split)
    assert all(len(splits) == 1 for splits in family_splits.values())
    specs = {spec.id: spec for spec in CASES}
    task_splits: dict[tuple[str, int], set[str]] = {}
    for split, case in _emitted():
        spec = specs[str(case["id"])]
        domain = domain_of(spec.upstream_file)
        assert case["task_family"] == task_family(domain, spec.task_id)
        assert str(case["origin_ref"]).endswith(f"{spec.upstream_file}#{spec.upstream_index}")
        airline_split = "validation" if spec.task_id <= 24 else "heldout"
        expected = "dev" if domain == "retail" else airline_split
        assert split == expected == SPLIT_OF_FAMILY[str(case["task_family"])]
        task_splits.setdefault((domain, spec.task_id), set()).add(split)
    assert all(len(splits) == 1 for splits in task_splits.values())


def test_selected_runs_match_their_task_and_trial() -> None:
    for spec in CASES:
        runs = load_runs(spec.upstream_file)
        assert [(r.task_id, r.trial) for r in runs].count((spec.task_id, spec.trial)) == 1


@pytest.mark.parametrize("family", ["airline", "retail"])
def test_no_reward_or_grading_field_leaks(family: str) -> None:
    upstream_file = f"gpt-4o-{family}.json"
    raw: list[dict[str, object]] = json.loads(
        (SOURCE_DIR / "historical_trajectories" / upstream_file).read_text(encoding="utf-8")
    )
    assert all(set(entry) == {"task_id", "trial", "traj"} for entry in raw)
    assert load_runs(upstream_file)
    for _, case in _emitted():
        assert not (_keys(case) & LABEL_KEYS)
        assert "reward" not in json.dumps(case["trajectory"]).lower()


def test_every_called_tool_is_in_the_domains_tool_list() -> None:
    for _, case in _emitted():
        trajectory = case["trajectory"]
        assert isinstance(trajectory, dict)
        steps: list[dict[str, dict[str, object]]] = trajectory["steps"]
        domain = "airline" if "airline" in str(case["task_family"]) else "retail"
        assert {step["tool_call"]["name"] for step in steps} <= set(TOOLS[domain])


def test_vendored_files_match_source_md() -> None:
    source_md = (SOURCE_DIR / "SOURCE.md").read_text(encoding="utf-8")
    rows = re.findall(
        r"^\| `([^`]+)` \| `[^`]+` \| `[0-9a-f]{64}` \| `([0-9a-f]{64})` \|$",
        source_md,
        flags=re.MULTILINE,
    )
    recorded = dict(rows)
    vendored = {
        str(path.relative_to(SOURCE_DIR)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in SOURCE_DIR.rglob("*")
        if path.is_file() and path.name not in {"SOURCE.md", "NOTICE"}
    }
    assert vendored == recorded
