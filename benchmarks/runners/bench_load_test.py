from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench_cases import CHECKS, SPLITS, Case
from bench_load import DATASETS_DIR, DatasetError, dataset_version, load_datasets


def _case(
    id_: str = "c1", check: str = "prompt_injection", **overrides: object
) -> dict[str, object]:
    case: dict[str, object] = {
        "id": id_,
        "check": check,
        "category": "payload_ignored",
        "source": "synthetic",
        "origin": "attest-seed",
        "task_family": "fam-dev",
        "label_status": "draft",
        "annotators": [],
        "trajectory": {
            "task": "t",
            "steps": [{"tool_call": {"name": "fetch", "output": "hello"}}],
            "final_answer": "a",
        },
        "expected": {"label": "none"},
        "notes": "",
    }
    case.update(overrides)
    return case


def _tree(root: Path, files: dict[tuple[str, str], list[dict[str, object]]]) -> Path:
    for check in CHECKS:
        (root / check).mkdir(parents=True, exist_ok=True)
        for split in SPLITS:
            rows = files.get((check, split), [])
            text = "".join(json.dumps(row) + "\n" for row in rows)
            (root / check / f"{split}.jsonl").write_text(text)
    return root


def test_seed_datasets_load_and_are_all_drafts() -> None:
    datasets = load_datasets(DATASETS_DIR)
    cases = [
        c
        for by_split in datasets.cases.values()
        for s in by_split.values()
        for c in s
        if c.origin == "attest-seed"
    ]
    assert len(cases) >= 20
    assert all(c.label_status == "draft" and c.source == "synthetic" for c in cases)
    assert all(c.notes.startswith("DRAFT") for c in cases)
    for check in CHECKS:
        assert datasets.split(check, "dev"), check
        assert datasets.split(check, "heldout"), check
        for split in SPLITS:
            assert (DATASETS_DIR / check / f"{split}.jsonl").is_file()
            seeds = [c for c in datasets.split(check, split) if c.origin == "attest-seed"]
            assert all(c.task_family == f"attest-seed/{check}/{split}" for c in seeds)
            assert all(c.origin_ref is None for c in seeds)
    assert len(datasets.version) == 64


def test_valid_tree_loads(tmp_path: Path) -> None:
    root = _tree(tmp_path, {("prompt_injection", "dev"): [_case()]})
    datasets = load_datasets(root)
    assert [c.id for c in datasets.split("prompt_injection", "dev")] == ["c1"]


def test_malformed_json_names_file_and_line(tmp_path: Path) -> None:
    root = _tree(tmp_path, {})
    (root / "role_adherence" / "dev.jsonl").write_text("\n{not json\n")
    with pytest.raises(DatasetError, match=r"role_adherence/dev.jsonl:2"):
        load_datasets(root)


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected": {"label": "in_scope"}},
        {"expected": {"label": "payload", "extra": 1}},
        {"source": "scraped"},
        {"id": "Has Spaces"},
        {"label_status": "confirmed", "annotators": ["AO"]},
        {"unknown_field": True},
    ],
)
def test_malformed_cases_are_rejected(tmp_path: Path, overrides: dict[str, object]) -> None:
    root = _tree(tmp_path, {("prompt_injection", "dev"): [_case(**overrides)]})
    with pytest.raises(DatasetError, match="invalid case"):
        load_datasets(root)


def test_confirmed_case_with_two_annotators_is_accepted() -> None:
    case = Case.model_validate(_case(label_status="confirmed", annotators=["AO", "JK"]))
    assert case.label_status == "confirmed"


def test_check_must_match_folder(tmp_path: Path) -> None:
    root = _tree(tmp_path, {("role_adherence", "dev"): [_case()]})
    with pytest.raises(DatasetError, match="lives in the 'role_adherence' folder"):
        load_datasets(root)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    other = _case(
        "c1", "role_adherence", expected={"label": "in_scope"}, category="in_scope_request"
    )
    root = _tree(
        tmp_path, {("prompt_injection", "dev"): [_case()], ("role_adherence", "dev"): [other]}
    )
    with pytest.raises(DatasetError, match="duplicate case id"):
        load_datasets(root)


def test_same_id_in_dev_and_heldout_is_rejected(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {("prompt_injection", "dev"): [_case()], ("prompt_injection", "heldout"): [_case()]},
    )
    with pytest.raises(DatasetError, match=r"in more than one split: c1 \(dev, heldout\)"):
        load_datasets(root)


def test_tool_labels_must_cover_every_call(tmp_path: Path) -> None:
    case = _case(check="tool_use", expected={"calls": [{"step": 3, "verdict": "correct"}]})
    root = _tree(tmp_path, {("tool_use", "dev"): [case]})
    with pytest.raises(DatasetError, match="label every tool call"):
        load_datasets(root)


def test_recovery_calls_need_a_recovery_label() -> None:
    case = _case(check="recovery", expected={"calls": [{"step": 0, "verdict": "correct"}]})
    with pytest.raises(ValueError, match="recovery"):
        Case.model_validate(case)


def test_duplicate_claims_are_rejected() -> None:
    claim = {"text": "x", "label": "supported"}
    case = _case(check="faithfulness", expected={"claims": [claim, claim]})
    with pytest.raises(ValueError, match="unique"):
        Case.model_validate(case)


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    root = _tree(tmp_path, {})
    (root / "tool_use" / "heldout.jsonl").unlink()
    with pytest.raises(DatasetError, match="missing"):
        load_datasets(root)


def test_dataset_version_changes_with_any_edit(tmp_path: Path) -> None:
    root = _tree(tmp_path, {("prompt_injection", "dev"): [_case()]})
    before = dataset_version(root)
    assert dataset_version(root) == before
    (root / "role_adherence" / "heldout.jsonl").write_text("\n")
    assert dataset_version(root) != before


def test_missing_files_are_allowed_for_a_partial_dataset(tmp_path: Path) -> None:
    root = tmp_path / "private"
    (root / "prompt_injection").mkdir(parents=True)
    (root / "prompt_injection" / "dev.jsonl").write_text(json.dumps(_case()) + "\n")
    datasets = load_datasets(root, allow_missing=True)
    assert [case.id for case in datasets.split("prompt_injection", "dev")] == ["c1"]
    assert datasets.split("faithfulness", "dev") == []


def test_missing_datasets_folder_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="not found"):
        load_datasets(tmp_path / "nope", allow_missing=True)
