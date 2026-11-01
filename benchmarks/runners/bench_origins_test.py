"""Case origins, task families, the validation split and external `<split>-<origin>` files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import annotate
import bench_load
from bench_cases import CHECKS, SPLITS, Case
from bench_load import DatasetError, case_files, dataset_version, load_datasets
from bench_write import write_cases


def _case(
    id_: str = "c1", check: str = "prompt_injection", **overrides: object
) -> dict[str, object]:
    case: dict[str, object] = {
        "id": id_,
        "check": check,
        "category": "payload_ignored",
        "source": "community",
        "origin": "tau-bench",
        "task_family": "tau-bench/retail",
        "origin_ref": "historical_trajectories/gpt-4o-retail.json#3",
        "label_status": "draft",
        "annotators": [],
        "trajectory": {
            "task": "t",
            "steps": [{"tool_call": {"name": "fetch", "output": "hello"}}],
            "final_answer": "a",
        },
        "expected": {"label": "none"},
    }
    if check == "role_adherence":
        case.update(category="in_scope_request", expected={"label": "in_scope"})
    case.update(overrides)
    return case


def _tree(root: Path, files: dict[str, list[dict[str, object]]] | None = None) -> Path:
    """Empty seed files for every check and split, plus `files` keyed `<check>/<file name>`."""
    for check in CHECKS:
        (root / check).mkdir(parents=True, exist_ok=True)
        for split in SPLITS:
            (root / check / f"{split}.jsonl").write_text("")
    for name, rows in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("".join(json.dumps(row) + "\n" for row in rows))
    return root


def test_three_splits() -> None:
    assert SPLITS == ("dev", "validation", "heldout")


def test_origin_fields_are_validated() -> None:
    case = Case.model_validate(_case())
    assert (case.origin, case.task_family) == ("tau-bench", "tau-bench/retail")
    assert case.origin_ref == "historical_trajectories/gpt-4o-retail.json#3"
    without_ref = _case()
    del without_ref["origin_ref"]
    assert Case.model_validate(without_ref).origin_ref is None
    assert "origin_ref" not in Case.model_validate(without_ref).model_dump(exclude_unset=True)


@pytest.mark.parametrize(
    "overrides",
    [
        {"origin": "Tau Bench"},
        {"origin": "-tau"},
        {"origin": "tau/bench"},
        {"task_family": "/retail"},
        {"task_family": "Retail"},
        {"task_family": ""},
        {"origin_ref": ""},
        {"origin_ref": 3},
    ],
)
def test_malformed_origin_fields_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Case.model_validate(_case(**overrides))


@pytest.mark.parametrize("field", ["origin", "task_family"])
def test_origin_and_task_family_are_required(field: str) -> None:
    case = _case()
    del case[field]
    with pytest.raises(ValueError, match=field):
        Case.model_validate(case)


def test_validation_split_loads(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"prompt_injection/validation.jsonl": [_case()]})
    assert [c.id for c in load_datasets(root).split("prompt_injection", "validation")] == ["c1"]


def test_missing_validation_file_is_rejected_unless_partial(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "tool_use" / "validation.jsonl").unlink()
    with pytest.raises(DatasetError, match=r"validation\.jsonl: case file is missing"):
        load_datasets(root)
    assert load_datasets(root, allow_missing=True).split("tool_use", "validation") == []


def test_external_files_join_their_split(tmp_path: Path) -> None:
    seed = _case("seed-1", origin="attest-seed", task_family="attest-seed/prompt_injection/dev")
    other = _case("agentdojo-1", origin="agentdojo", task_family="agentdojo/workspace")
    root = _tree(
        tmp_path,
        {
            "prompt_injection/dev.jsonl": [seed],
            "prompt_injection/dev-tau-bench.jsonl": [_case("tau-1")],
            "prompt_injection/dev-agentdojo.jsonl": [other],
            "prompt_injection/heldout-tau-bench.jsonl": [
                _case("tau-2", task_family="tau-bench/airline")
            ],
        },
    )
    datasets = load_datasets(root)
    assert [c.id for c in datasets.split("prompt_injection", "dev")] == [
        "seed-1",
        "agentdojo-1",
        "tau-1",
    ]
    assert [c.id for c in datasets.split("prompt_injection", "heldout")] == ["tau-2"]
    assert [p.name for p in case_files(root, "prompt_injection", "dev")] == [
        "dev.jsonl",
        "dev-agentdojo.jsonl",
        "dev-tau-bench.jsonl",
    ]


def test_external_files_load_in_a_private_dataset(tmp_path: Path) -> None:
    root = tmp_path / "private"
    (root / "prompt_injection").mkdir(parents=True)
    (root / "prompt_injection" / "validation-tau-bench.jsonl").write_text(
        json.dumps(_case()) + "\n"
    )
    datasets = load_datasets(root, allow_missing=True)
    assert [c.id for c in datasets.split("prompt_injection", "validation")] == ["c1"]


def test_external_file_must_hold_only_its_origin(tmp_path: Path) -> None:
    rows = [_case("tau-1"), _case("dojo-1", origin="agentdojo")]
    root = _tree(tmp_path, {"prompt_injection/dev-tau-bench.jsonl": rows})
    with pytest.raises(
        DatasetError,
        match=r"dev-tau-bench.jsonl:2: case 'dojo-1' has origin 'agentdojo' but lives in "
        r"the 'tau-bench' file",
    ):
        load_datasets(root)


@pytest.mark.parametrize(
    "name",
    [
        "prompt_injection/valid-tau-bench.jsonl",
        "prompt_injection/dev_tau.jsonl",
        "prompt_injection/dev-Tau.jsonl",
        "prompt_injection/dev-tau-bench.JSONL",
        "prompt_injection/Dev-tau-bench.jsonl",
        "prompt_injection/dev-tau-bench.json",
        "prompt_injection/heldout-dev.jsonl",
        "prompt_injection/dev-validation.jsonl",
        "prompt_injection/README.md",
        "prompt_injection/sub/dev-tau-bench.jsonl",
        "prompt-injection/dev-tau-bench.jsonl",
        "notes.txt",
        "dev.jsonl",
    ],
)
@pytest.mark.parametrize("private", [False, True])
def test_unrecognised_case_files_are_rejected(tmp_path: Path, name: str, private: bool) -> None:
    root = _tree(tmp_path, {name: [_case()]})
    with pytest.raises(DatasetError, match=r"unrecognised entries in the datasets folder"):
        load_datasets(root, allow_missing=private)


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("prompt-injection/dev-tau-bench.jsonl", r"prompt-injection: unknown folder"),
        ("prompt_injection/sub/dev-tau-bench.jsonl", r"prompt_injection/sub: subfolders"),
        ("prompt_injection/heldout-dev.jsonl", r"heldout-dev.jsonl: unrecognised case file"),
        ("notes.txt", r"notes.txt: unknown file"),
    ],
)
def test_each_unknown_entry_is_named(tmp_path: Path, name: str, problem: str) -> None:
    root = _tree(tmp_path, {name: [_case()]})
    with pytest.raises(DatasetError, match=problem):
        load_datasets(root)


def test_hidden_entries_and_a_top_level_readme_are_allowed(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "README.md").write_text("# cases\n")
    (root / ".DS_Store").write_text("")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref")
    (root / "prompt_injection" / ".gitkeep").write_text("")
    (root / "prompt_injection" / ".DS_Store").write_text("")
    (root / "prompt_injection" / ".cache").mkdir()
    assert load_datasets(root).split("prompt_injection", "dev") == []


def test_public_split_files_hold_only_seed_cases(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"prompt_injection/dev.jsonl": [_case("tau-1")]})
    with pytest.raises(
        DatasetError,
        match=r"dev.jsonl:1: case 'tau-1' has origin 'tau-bench', but a public dev.jsonl holds "
        r"only 'attest-seed' cases; put external cases in dev-<origin>.jsonl",
    ):
        load_datasets(root, public=True)
    assert [c.id for c in load_datasets(root).split("prompt_injection", "dev")] == ["tau-1"]


def test_the_public_datasets_default_to_the_seed_origin_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path, {"prompt_injection/dev.jsonl": [_case("tau-1")]})
    monkeypatch.setattr(bench_load, "DATASETS_DIR", root)
    with pytest.raises(DatasetError, match="holds only 'attest-seed' cases"):
        load_datasets(root)
    assert len(load_datasets(root, public=False).split("prompt_injection", "dev")) == 1


def test_private_split_files_may_hold_any_origin(tmp_path: Path) -> None:
    root = tmp_path / "private"
    (root / "prompt_injection").mkdir(parents=True)
    rows = [_case("tau-1"), _case("own-1", origin="vera-support", task_family="vera/billing")]
    (root / "prompt_injection" / "dev.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    datasets = load_datasets(root, allow_missing=True)
    assert [c.origin for c in datasets.split("prompt_injection", "dev")] == [
        "tau-bench",
        "vera-support",
    ]


def test_a_task_family_may_not_span_splits_across_checks(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "prompt_injection/dev-tau-bench.jsonl": [_case("tau-1")],
            "role_adherence/heldout-tau-bench.jsonl": [_case("tau-2", "role_adherence")],
        },
    )
    with pytest.raises(
        DatasetError,
        match=r"task_family\(s\) in more than one split.*tau-bench/retail "
        r"\(dev, heldout\)",
    ):
        load_datasets(root)


def test_a_task_family_may_span_checks_within_one_split(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "prompt_injection/validation-tau-bench.jsonl": [_case("tau-1")],
            "role_adherence/validation-tau-bench.jsonl": [_case("tau-2", "role_adherence")],
        },
    )
    datasets = load_datasets(root)
    assert len(datasets.split("role_adherence", "validation")) == 1


def test_an_id_in_dev_and_validation_is_rejected(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "prompt_injection/dev-tau-bench.jsonl": [_case("tau-1", task_family="a")],
            "prompt_injection/validation-tau-bench.jsonl": [_case("tau-1", task_family="b")],
        },
    )
    with pytest.raises(DatasetError, match=r"tau-1 \(dev, validation\)"):
        load_datasets(root)


def test_dataset_version_covers_external_files(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    before = dataset_version(root)
    external = root / "prompt_injection" / "dev-tau-bench.jsonl"
    external.write_text(json.dumps(_case()) + "\n")
    added = dataset_version(root)
    assert added != before
    external.write_text(json.dumps(_case(category="other")) + "\n")
    assert dataset_version(root) not in {before, added}
    assert load_datasets(root).version == dataset_version(root)
    external.unlink()
    assert dataset_version(root) == before


def test_merge_writes_confirmed_cases_into_external_files(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"prompt_injection/dev-tau-bench.jsonl": [_case("tau-1")]})
    case = load_datasets(root).split("prompt_injection", "dev")[0]
    confirmed = case.model_copy(update={"label_status": "confirmed", "annotators": ["po", "vk"]})
    assert write_cases(root, {"tau-1": confirmed}) == 1
    [written] = load_datasets(root).split("prompt_injection", "dev")
    assert written.label_status == "confirmed" and written.origin == "tau-bench"
    assert written.origin_ref == case.origin_ref


def test_template_takes_the_validation_split(tmp_path: Path) -> None:
    root = _tree(tmp_path / "datasets", {"prompt_injection/validation-tau-bench.jsonl": [_case()]})
    labels = tmp_path / "labels"
    argv = ["--datasets", str(root), "--labels", str(labels)]
    assert annotate.main([*argv, "template", "po", "--split", "validation"]) == 0
    assert [p.name for p in (labels / "po").iterdir()] == ["c1.json"]


@pytest.mark.parametrize(
    ("dev_family", "heldout_family"),
    [
        ("tau-bench/airline", "tau-bench/airline/25-49"),
        ("tau-bench/airline/25-49", "tau-bench"),
        ("tau-bench/airline/", "tau-bench/airline//25-49"),
    ],
)
def test_a_family_nested_under_one_in_another_split_is_rejected(
    tmp_path: Path, dev_family: str, heldout_family: str
) -> None:
    root = _tree(
        tmp_path,
        {
            "prompt_injection/dev-tau-bench.jsonl": [_case("tau-1", task_family=dev_family)],
            "role_adherence/heldout-tau-bench.jsonl": [
                _case("tau-2", "role_adherence", task_family=heldout_family)
            ],
        },
    )
    with pytest.raises(DatasetError, match=r"nested under a family in another split"):
        load_datasets(root)


def test_families_sharing_a_name_prefix_but_not_a_path_may_split(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "prompt_injection/dev-tau-bench.jsonl": [
                _case("tau-1", task_family="tau-bench/airline-0-24"),
                _case("tau-3", task_family="tau-bench/airline/0-24"),
            ],
            "prompt_injection/heldout-tau-bench.jsonl": [
                _case("tau-2", task_family="tau-bench/airline-25-49")
            ],
        },
    )
    datasets = load_datasets(root)
    assert len(datasets.split("prompt_injection", "heldout")) == 1


def test_seed_families_are_siblings_not_prefixes() -> None:
    families = {
        case.task_family
        for by_split in load_datasets().cases.values()
        for split_cases in by_split.values()
        for case in split_cases
        if case.origin == "attest-seed"
    }
    assert families and all(f.count("/") == 2 for f in families)
