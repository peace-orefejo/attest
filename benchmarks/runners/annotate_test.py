from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import annotate
from bench_agreement import agreement, cohen_kappa
from bench_annotations import AnnotationError
from bench_cases import Case, CheckName
from bench_label_files import load_annotations
from bench_load import DATASETS_DIR, load_datasets
from bench_merge import Adjudication, merge
from bench_write import write_cases


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


def test_labels_for_changed_items_are_stale_not_fatal(datasets: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _template(datasets, labels, "po", "tool_use")
    _fill(labels, "po", "tool-prohibited-delete", {"calls": [{"step": 3, "verdict": "correct"}]})
    loaded = load_annotations(labels, _cases(datasets))
    [stale] = loaded.stale
    assert stale.path.stem == "tool-prohibited-delete" and "items to label changed" in stale.reason


def test_labels_given_before_the_run_changed_are_never_confirmed(
    datasets: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = tmp_path / "labels"
    case_id = "inj-payload-obeyed"
    for name in ("po", "vk"):
        _template(datasets, labels, name, "prompt_injection")
        _fill(labels, name, case_id, {"label": "compromised"})
    assert (
        case_id
        in merge(
            load_annotations(labels, _cases(datasets)).annotations, _cases(datasets), []
        ).confirmed
    )

    path = datasets / "prompt_injection" / "dev.jsonl"
    lines = path.read_text().splitlines()
    for index, line in enumerate(lines):
        case = json.loads(line)
        if case["id"] == case_id:
            case["trajectory"]["final_answer"] = "Hello."
            lines[index] = json.dumps(case)
    path.write_text("\n".join(lines) + "\n")

    cases = _cases(datasets)
    loaded = load_annotations(labels, cases)
    assert {s.reason for s in loaded.stale} == {"the run changed after it was labelled"}
    assert case_id not in merge(loaded.annotations, cases, []).confirmed
    capsys.readouterr()
    _template(datasets, labels, "po", "prompt_injection")
    assert f"stale: {labels / 'po' / case_id}.json" in capsys.readouterr().out


def test_label_files_may_not_carry_a_run_label(datasets: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _template(datasets, labels, "po", "faithfulness")
    case_id = _dev_ids(datasets, "faithfulness")[0]
    data = json.loads((labels / "po" / f"{case_id}.json").read_text())
    claims = [{"text": c["text"], "label": "supported"} for c in data["labels"]["claims"]]
    for run_label in ("block", None):
        _fill(labels, "po", case_id, {"claims": claims, "run_label": run_label})
        with pytest.raises(AnnotationError, match="run_label"):
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
        ruling="2026-11-01 injection labels",
    )
    outcome = merge(load_annotations(labels, cases).annotations, cases, [bad])
    assert "isn't valid" in outcome.unresolved[case_id][0]


def test_cli_agreement_and_dry_run_merge(
    datasets: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = tmp_path / "labels"
    argv = ["--datasets", str(datasets), "--labels", str(labels)]
    log = ["--adjudications", str(tmp_path / "adjudications.jsonl")]
    for name in ("po", "vk"):
        _template(datasets, labels, name, "prompt_injection")
        _fill(labels, name, "inj-clean-output", {"label": "none"})
    capsys.readouterr()

    assert annotate.main([*argv, "agreement", "po", "vk"]) == 0
    out = capsys.readouterr()
    assert "| prompt_injection | label | 1 | 1 | 100% 1/1 | n/a |" in out.out
    assert "unfinished" in out.err

    before = (datasets / "prompt_injection" / "dev.jsonl").read_text()
    assert annotate.main([*argv, "merge", *log]) == 0
    assert "confirmed      inj-clean-output" in capsys.readouterr().out
    assert (datasets / "prompt_injection" / "dev.jsonl").read_text() == before

    assert annotate.main([*argv, "agreement", "po", "nobody"]) == 2


def _settle(case_id: str, label: str, **overrides: object) -> Adjudication:
    fields: dict[str, object] = {
        "case_id": case_id,
        "dimension": "label",
        "subject": "run",
        "label": label,
        "how": "discussion",
        "decided_by": ["po", "vk"],
        "reason": "r",
    }
    fields.update(overrides)
    return Adjudication.model_validate(fields)


def test_adjudications_are_validated(datasets: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    cases = _cases(datasets)
    case_id = "inj-clean-output"
    for name, label in (("po", "none"), ("vk", "none"), ("zz", "none")):
        _template(datasets, labels, name, "prompt_injection")
        _fill(labels, name, case_id, {"label": label})
    annotations = load_annotations(labels, cases).annotations

    with pytest.raises(ValueError, match="matches no item"):
        merge(annotations, cases, [_settle(case_id, "none", subject="runn")])
    with pytest.raises(ValueError, match="matches no item"):
        merge(annotations, cases, [_settle("no-such-case", "none")])
    with pytest.raises(ValueError, match="more than once"):
        merge(annotations, cases, [_settle(case_id, "none"), _settle(case_id, "payload")])
    with pytest.raises(ValueError, match="rulings-log entry"):
        _settle(case_id, "payload", how="owner_ruling")

    outcome = merge(annotations, cases, [_settle(case_id, "payload")])
    assert "only an owner ruling can" in outcome.unresolved[case_id][0]
    ruling = _settle(case_id, "payload", how="owner_ruling", decided_by=["owner"], ruling="r1")
    confirmed = merge(annotations, cases, [ruling]).confirmed[case_id]
    assert confirmed.expected.model_dump()["label"] == "payload"
    assert confirmed.annotators == ["po", "vk", "zz"]


def test_a_discussion_must_be_between_the_case_annotators(datasets: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    cases = _cases(datasets)
    case_id = "inj-clean-output"
    for name, label in (("po", "none"), ("vk", "payload")):
        _template(datasets, labels, name, "prompt_injection")
        _fill(labels, name, case_id, {"label": label})
    annotations = load_annotations(labels, cases).annotations
    outsider = _settle(case_id, "none", decided_by=["po", "qq"])
    assert (
        "qq didn't label this case" in merge(annotations, cases, [outsider]).unresolved[case_id][0]
    )
    assert case_id in merge(annotations, cases, [_settle(case_id, "none")]).confirmed


def test_three_annotators_with_one_dissent_stay_unresolved(datasets: Path, tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    cases = _cases(datasets)
    case_id = "inj-clean-output"
    for name, label in (("po", "none"), ("vk", "none"), ("zz", "payload")):
        _template(datasets, labels, name, "prompt_injection")
        _fill(labels, name, case_id, {"label": label})
    outcome = merge(load_annotations(labels, cases).annotations, cases, [])
    assert "po none, vk none, zz payload" in outcome.unresolved[case_id][0]


def test_cli_merge_write_confirms_faithfulness_and_recovery(
    datasets: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = tmp_path / "labels"
    argv = ["--datasets", str(datasets), "--labels", str(labels)]
    log = ["--adjudications", str(tmp_path / "adjudications.jsonl")]
    before = _cases(datasets)
    picked = [_dev_ids(datasets, "faithfulness")[0], _dev_ids(datasets, "recovery")[0]]
    for name in ("po", "vk"):
        for check in ("faithfulness", "recovery"):
            _template(datasets, labels, name, check)
        for case_id in picked:
            data = json.loads((labels / name / f"{case_id}.json").read_text())
            _fill(labels, name, case_id, before[case_id].expected.model_dump(exclude={"run_label"}))
            assert data["labels"] != before[case_id].expected.model_dump()
    capsys.readouterr()
    assert annotate.main([*argv, "merge", "--write", *log]) == 0
    assert "wrote 2 confirmed case(s)" in capsys.readouterr().out
    after = _cases(datasets)
    for case_id in picked:
        assert after[case_id].label_status == "confirmed"
        assert after[case_id].expected == before[case_id].expected
        assert after[case_id].trajectory == before[case_id].trajectory


def test_private_labels_must_stay_out_of_the_repo(
    datasets: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        annotate.main(["--datasets", str(datasets), "template", "po"])
    assert exc.value.code == 2
    assert "keep its labels out of this repository" in capsys.readouterr().err
    labels = ["--labels", str(tmp_path / "labels")]
    with pytest.raises(SystemExit):
        annotate.main(["--datasets", str(datasets), *labels, "merge"])
    assert "adjudications" in capsys.readouterr().err


def test_annotator_names_and_pairs_are_checked(
    datasets: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--datasets", str(datasets), "--labels", str(tmp_path / "labels")]
    for bad in ("po\n", "../x", "PO"):
        with pytest.raises(SystemExit):
            annotate.main([*argv, "template", bad])
    with pytest.raises(SystemExit):
        annotate.main([*argv, "agreement", "po", "po"])
    assert "two different annotators" in capsys.readouterr().err
