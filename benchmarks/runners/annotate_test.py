from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import annotate
from bench_agreement import agreement, cohen_kappa
from bench_annotations import AnnotationError, load_annotations
from bench_cases import Case, CheckName
from bench_load import DATASETS_DIR, load_datasets
from bench_merge import Adjudication, merge, write_cases


@pytest.fixture
def datasets(tmp_path: Path) -> Path:
    root = tmp_path / "datasets"
    shutil.copytree(DATASETS_DIR, root)
    return root


def _cases(root: Path) -> dict[str, Case]:
    loaded = load_datasets(root)
    return {c.id: c for by in loaded.cases.values() for cs in by.values() for c in cs}


def _dev_ids(root: Path, check: CheckName) -> list[str]:
    return sorted(c.id for c in load_datasets(root).split(check, "dev"))


def _template(datasets: Path, labels: Path, annotator: str, check: str) -> None:
    argv = ["--datasets", str(datasets), "--labels", str(labels)]
    assert annotate.main([*argv, "template", annotator, "--check", check]) == 0


def _fill(
    labels: Path, annotator: str, case_id: str, labels_value: object, **extra: object
) -> None:
    path = labels / annotator / f"{case_id}.json"
    data = json.loads(path.read_text())
    data.update(labels=labels_value, confidence="high", rationale="because", **extra)
    path.write_text(json.dumps(data))


def test_kappa_matches_hand_computation() -> None:
    # 4 items, 3 agree; rater 1 says a twice, rater 2 three times -> chance (2*3 + 2*1) / 16
    pairs = [("a", "a"), ("a", "a"), ("b", "b"), ("b", "a")]
    assert cohen_kappa(pairs) == pytest.approx((0.75 - 0.5) / (1 - 0.5))
    assert cohen_kappa([("a", "a"), ("b", "b")]) == 1.0
    assert cohen_kappa([("a", "a"), ("a", "a")]) is None
    assert cohen_kappa([]) is None


def test_template_is_blind_and_unfinished_files_are_skipped(datasets: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _template(datasets, labels, "po", "faithfulness")
    files = sorted((labels / "po").glob("*.json"))
    cases = _cases(datasets)
    assert [f.stem for f in files] == _dev_ids(datasets, "faithfulness")
    template = json.loads(files[0].read_text())
    assert all(claim["label"] is None for claim in template["labels"]["claims"])
    assert template["trajectory"]["task"] == cases[files[0].stem].trajectory.task
    assert "expected" not in template and "notes" not in template

    loaded = load_annotations(labels, cases)
    assert loaded.annotations == {"po": {}} and len(loaded.unfinished) == len(files)


def test_labels_must_match_the_case(datasets: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _template(datasets, labels, "po", "tool_use")
    _fill(labels, "po", "tool-prohibited-delete", {"calls": [{"step": 3, "verdict": "correct"}]})
    with pytest.raises(AnnotationError, match="don't match the case's items"):
        load_annotations(labels, _cases(datasets))


def test_agreement_merge_and_write(datasets: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    cases = _cases(datasets)
    injection = _dev_ids(datasets, "prompt_injection")
    for name in ("po", "vk"):
        _template(datasets, labels, name, "prompt_injection")
        for case_id in injection:
            _fill(labels, name, case_id, {"label": "none"})
    # vk disagrees on one case; po marks another ambiguous
    disputed, ambiguous = injection[0], injection[1]
    _fill(labels, "vk", disputed, {"label": "payload"})
    _fill(labels, "po", ambiguous, {"label": "none"}, ambiguous=True)

    annotations = load_annotations(labels, cases).annotations
    report = agreement(annotations, cases, "po", "vk")
    [dimension] = report.dimensions
    assert (dimension.items, dimension.agreed) == (len(injection), len(injection) - 1)
    assert dimension.ambiguous_cases == 1
    assert [(d.case_id, d.labels) for d in report.disagreements] == [
        (disputed, {"po": "none", "vk": "payload"})
    ]

    outcome = merge(annotations, cases, [])
    assert "unsettled" in outcome.unresolved[disputed][0]
    assert "ambiguous" in outcome.unresolved[ambiguous][0]

    settle = Adjudication(
        case_id=disputed,
        dimension="label",
        subject="run",
        label="payload",
        how="discussion",
        decided_by=["po", "vk"],
        reason="the output does carry an instruction",
    )
    outcome = merge(annotations, cases, [settle])
    confirmed = outcome.confirmed[disputed]
    assert confirmed.label_status == "confirmed" and confirmed.annotators == ["po", "vk"]
    assert confirmed.expected.model_dump()["label"] == "payload"
    assert "settled by discussion" in confirmed.notes
    assert set(outcome.unresolved) == {ambiguous}

    assert write_cases(datasets, outcome.confirmed) == len(outcome.confirmed)
    reloaded = _cases(datasets)
    assert reloaded[disputed] == confirmed
    assert reloaded[ambiguous] == cases[ambiguous]


def test_invalid_adjudicated_label_is_reported(datasets: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    cases = _cases(datasets)
    case_id = "inj-clean-output"
    for name, label in (("po", "none"), ("vk", "payload")):
        _template(datasets, labels, name, "prompt_injection")
        _fill(labels, name, case_id, {"label": label})
    bad = Adjudication(
        case_id=case_id,
        dimension="label",
        subject="run",
        label="nonsense",
        how="owner_ruling",
        decided_by=["po"],
        reason="r",
    )
    outcome = merge(load_annotations(labels, cases).annotations, cases, [bad])
    assert "isn't valid" in outcome.unresolved[case_id][0]


def test_cli_agreement_and_dry_run_merge(
    datasets: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = tmp_path / "labels"
    argv = ["--datasets", str(datasets), "--labels", str(labels)]
    for name in ("po", "vk"):
        _template(datasets, labels, name, "prompt_injection")
        _fill(labels, name, "inj-clean-output", {"label": "none"})
    capsys.readouterr()

    assert annotate.main([*argv, "agreement", "po", "vk"]) == 0
    out = capsys.readouterr()
    assert "| prompt_injection | label | 1 | 1 | 100% 1/1 | n/a |" in out.out
    assert "unfinished" in out.err

    before = (datasets / "prompt_injection" / "dev.jsonl").read_text()
    assert annotate.main([*argv, "merge"]) == 0
    assert "confirmed      inj-clean-output" in capsys.readouterr().out
    assert (datasets / "prompt_injection" / "dev.jsonl").read_text() == before

    assert annotate.main([*argv, "agreement", "po", "nobody"]) == 2
