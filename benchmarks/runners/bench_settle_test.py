"""`annotate.py settle`: validation, --replace, stale discussions, the private-path guard and the
log's locking; and atomic writes of confirmed cases."""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path

import pytest

import annotate
from bench_adjudications import Adjudication, index_adjudications, load_adjudications
from bench_annotations import run_sha256
from bench_cases import Case
from bench_label_files import load_annotations
from bench_load import DATASETS_DIR, load_datasets
from bench_merge import merge
from bench_write import write_cases

CASE = "inj-clean-output"


@pytest.fixture
def datasets(tmp_path: Path) -> Path:
    root = tmp_path / "datasets"
    shutil.copytree(DATASETS_DIR, root)
    return root


def _cases(root: Path) -> dict[str, Case]:
    loaded = load_datasets(root)
    return {c.id: c for by in loaded.cases.values() for cs in by.values() for c in cs}


def _label(datasets: Path, labels: Path, given: dict[str, str], case_id: str = CASE) -> None:
    """Each annotator labels `case_id`'s run with their label, over any earlier file."""
    for name, label in given.items():
        argv = ["--datasets", str(datasets), "--labels", str(labels)]
        assert annotate.main([*argv, "template", name, "--check", "prompt_injection"]) == 0
        path = labels / name / f"{case_id}.json"
        data = json.loads(path.read_text())
        data.update(labels={"label": label}, confidence="high", rationale="because")
        path.write_text(json.dumps(data))


class _Paths:
    def __init__(self, datasets: Path, tmp_path: Path) -> None:
        self.datasets, self.labels, self.log = datasets, tmp_path / "labels", tmp_path / "adj.jsonl"

    def settle(self, *args: str, labels: Path | None = None, log: Path | None = None) -> int:
        return annotate.main(
            [
                "--datasets",
                str(self.datasets),
                "--labels",
                str(labels or self.labels),
                "settle",
                *args,
                "--adjudications",
                str(log or self.log),
            ]
        )

    def merge(self, *extra: str) -> int:
        argv = ["--datasets", str(self.datasets), "--labels", str(self.labels), "merge"]
        return annotate.main([*argv, "--adjudications", str(self.log), *extra])


@pytest.fixture
def paths(datasets: Path, tmp_path: Path) -> _Paths:
    return _Paths(datasets, tmp_path)


DISCUSS = [CASE, "label", "run", "none", "--how", "discussion", "--by", "po", "vk"]
RULE = [CASE, "label", "run", "payload", "--how", "owner_ruling", "--ruling", "r1", "--by", "po"]


@pytest.mark.parametrize(
    ("argv", "problem"),
    [
        ([CASE, "label", "run", "nonsense", "--ruling", "r1"], "'nonsense' isn't a"),
        ([CASE, "label", "run", "none", "--ruling", " "], "needs --ruling"),
        ([CASE, "label", "step 0", "none", "--ruling", "r1"], "no item label 'step 0'"),
        (["rec-retried", "verdict", "step 0", "retried", "--ruling", "r1"], "verdict label"),
        (["rec-retried", "recovery", "step 0", "correct", "--ruling", "r1"], "recovery label"),
    ],
)
def test_settle_refuses_a_label_or_item_the_case_doesnt_have(
    paths: _Paths, capsys: pytest.CaptureFixture[str], argv: list[str], problem: str
) -> None:
    assert paths.settle(*argv, "--how", "owner_ruling", "--by", "po", "--reason", "r") == 2
    assert problem in capsys.readouterr().err
    assert not paths.log.exists()


def test_recovery_cases_keep_verdict_and_recovery_labels_apart(paths: _Paths) -> None:
    rule = ["--how", "owner_ruling", "--ruling", "r1", "--by", "po", "--reason", "r"]
    assert paths.settle("rec-retried", "verdict", "step 0", "error_silent", *rule) == 0
    assert paths.settle("rec-retried", "recovery", "step 0", "silent", *rule) == 0
    assert [x.label for x in load_adjudications(paths.log)] == ["error_silent", "silent"]


@pytest.mark.parametrize(
    ("by", "reason", "problem"),
    [
        (["PO"], "r", "--by names are lowercase"),
        (["../x"], "r", "--by names are lowercase"),
        (["po"], "   ", "--reason is blank"),
    ],
)
def test_settle_refuses_bad_names_and_a_blank_reason(
    paths: _Paths, capsys: pytest.CaptureFixture[str], by: list[str], reason: str, problem: str
) -> None:
    assert paths.settle(*RULE[:-2], "--by", *by, "--reason", reason) == 2
    assert problem in capsys.readouterr().err
    assert not paths.log.exists()


def test_a_discussion_must_be_by_exactly_the_annotators_who_still_disagree(
    paths: _Paths, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(paths.datasets, paths.labels, {"po": "none"})
    assert paths.settle(*DISCUSS, "--reason", "r") == 2
    assert "only ['po'] has finished, current labels" in capsys.readouterr().err

    _label(paths.datasets, paths.labels, {"vk": "none"})
    assert paths.settle(*DISCUSS, "--reason", "r") == 2
    assert "nothing to settle; only an owner ruling" in capsys.readouterr().err

    _label(paths.datasets, paths.labels, {"vk": "payload"})
    for by in (["po"], ["po", "vk", "zz"], ["po", "po", "vk"]):
        assert paths.settle(*DISCUSS[:-2], *by, "--reason", "r") == 2
        assert "exactly the annotators who labelled it, po vk" in capsys.readouterr().err
    assert not paths.log.exists()

    assert paths.settle(*DISCUSS, "--reason", " data only ") == 0
    [entry] = load_adjudications(paths.log)
    assert entry.labels == {"po": "none", "vk": "payload"} and entry.reason == "data only"
    assert entry.settled_at is not None


def test_replace_supersedes_an_entry_and_keeps_the_log_append_only(
    paths: _Paths, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(paths.datasets, paths.labels, {"po": "none", "vk": "payload"})
    assert paths.settle(*DISCUSS, "--reason", "r", "--replace") == 2
    assert "no current entry to replace" in capsys.readouterr().err

    assert paths.settle(*DISCUSS, "--reason", "first") == 0
    assert paths.settle(*RULE, "--reason", "second") == 2
    assert "pass --replace" in capsys.readouterr().err
    first_line = paths.log.read_text()
    assert paths.settle(*RULE, "--reason", "second", "--replace") == 0
    assert paths.settle(*DISCUSS, "--reason", "third", "--replace") == 0
    assert paths.log.read_text().startswith(first_line)

    first, second, third = load_adjudications(paths.log)
    assert second.replaces == first.entry_id and third.replaces == second.entry_id
    cases = _cases(paths.datasets)
    outcome = merge(
        load_annotations(paths.labels, cases).annotations, cases, load_adjudications(paths.log)
    )
    assert outcome.confirmed[CASE].expected.model_dump()["label"] == "none"
    assert "third" in outcome.confirmed[CASE].notes


def _entry(label: str, **overrides: object) -> Adjudication:
    fields: dict[str, object] = {
        "case_id": CASE,
        "dimension": "label",
        "subject": "run",
        "label": label,
        "how": "owner_ruling",
        "decided_by": ["po"],
        "reason": "r",
        "ruling": "r1",
        "run_sha256": run_sha256(_cases(DATASETS_DIR)[CASE]),
    }
    fields.update(overrides)
    return Adjudication.model_validate(fields)


def test_a_broken_replacement_is_refused() -> None:
    cases = _cases(DATASETS_DIR)
    first = _entry("none")
    other = _entry(
        "none", case_id="inj-payload-obeyed", run_sha256=run_sha256(cases["inj-payload-obeyed"])
    )
    for log, problem in (
        ([first, _entry("payload", replaces="0" * 16)], "no earlier entry"),
        ([first, other.model_copy(update={"replaces": first.entry_id})], "another item"),
        (
            [
                first,
                _entry("payload", replaces=first.entry_id),
                _entry("compromised", replaces=first.entry_id),
            ],
            "already replaced",
        ),
    ):
        with pytest.raises(ValueError, match=problem):
            index_adjudications(log, cases)
    chained = [first, _entry("payload", replaces=first.entry_id)]
    assert index_adjudications(chained, cases).settled[(CASE, ("label", "run"))].label == "payload"


def test_a_discussion_goes_stale_when_the_labels_it_settled_change(
    paths: _Paths, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(paths.datasets, paths.labels, {"po": "none", "vk": "payload"})
    assert paths.settle(*DISCUSS, "--reason", "data only") == 0
    assert paths.merge() == 0
    assert f"confirmed      {CASE}" in capsys.readouterr().out

    _label(paths.datasets, paths.labels, {"po": "payload", "vk": "compromised"})
    assert paths.merge("--write") == 0
    out = capsys.readouterr()
    assert (
        f"not confirmed  {CASE}: label 'run' is unsettled (po payload, vk compromised)" in out.out
    )
    assert f"stale adjudication of {CASE} label 'run': the labels changed" in out.err
    assert "then po none, vk payload, now po payload, vk compromised" in out.err
    assert _cases(paths.datasets)[CASE].label_status == "draft"

    assert paths.settle(*DISCUSS[:3], "payload", *DISCUSS[4:], "--reason", "r") == 2
    assert paths.settle(*DISCUSS[:3], "payload", *DISCUSS[4:], "--reason", "r", "--replace") == 0
    assert paths.merge() == 0
    assert f"confirmed      {CASE}" in capsys.readouterr().out


def test_an_owner_ruling_survives_relabelling(
    paths: _Paths, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(paths.datasets, paths.labels, {"po": "none", "vk": "payload"})
    assert paths.settle(*RULE, "--reason", "r") == 0
    _label(paths.datasets, paths.labels, {"po": "compromised", "vk": "compromised"})
    capsys.readouterr()
    assert paths.merge() == 0
    out = capsys.readouterr()
    assert f"confirmed      {CASE}" in out.out and "stale" not in out.err


def test_private_settle_is_held_to_the_paths_it_uses(
    paths: _Paths, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inside_log = annotate.PRIVATE_DIR.parent / "annotations" / "settle-test.jsonl"
    with pytest.raises(SystemExit):
        paths.settle(*RULE, "--reason", "r", log=inside_log)
    assert "--adjudications" in capsys.readouterr().err and not inside_log.exists()

    in_repo_labels = annotate.PRIVATE_DIR.parent / "annotations" / "labels"
    assert paths.settle(*RULE, "--reason", "r", labels=in_repo_labels) == 0
    with pytest.raises(SystemExit):
        paths.settle(*DISCUSS, "--reason", "r", "--replace", labels=in_repo_labels)
    assert "--labels" in capsys.readouterr().err

    target = annotate.PRIVATE_DIR.parent / "annotations" / "symlink-test-adj.jsonl"
    linked = tmp_path / "linked.jsonl"
    linked.symlink_to(target)
    with pytest.raises(SystemExit):
        paths.settle(*RULE, "--reason", "r", log=linked)
    assert "inside it" in capsys.readouterr().err and not target.exists()


def test_settling_through_a_symlinked_log_appends_to_its_target(
    paths: _Paths, tmp_path: Path
) -> None:
    target = tmp_path / "elsewhere" / "adjudications.jsonl"
    target.parent.mkdir()
    paths.log.symlink_to(target)
    assert paths.settle(*RULE, "--reason", "r") == 0
    assert paths.log.is_symlink() and len(load_adjudications(target)) == 1


def test_concurrent_settles_both_land_whole(datasets: Path, tmp_path: Path) -> None:
    log = tmp_path / "adj.jsonl"
    ids = sorted(c.id for c in load_datasets(datasets).split("prompt_injection", "dev"))
    results: list[int] = []

    def settle(case_id: str) -> None:
        argv = ["--datasets", str(datasets), "--labels", str(tmp_path / "labels"), "settle"]
        rule = ["--how", "owner_ruling", "--ruling", "r1", "--by", "po", "--reason", "r" * 2000]
        log_flag = ["--adjudications", str(log)]
        results.append(annotate.main([*argv, case_id, "label", "run", "none", *rule, *log_flag]))

    threads = [threading.Thread(target=settle, args=(case_id,)) for case_id in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [0] * len(ids)
    assert sorted(x.case_id for x in load_adjudications(log)) == ids


def test_write_cases_replaces_each_file_atomically(
    datasets: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = datasets / "prompt_injection" / "dev.jsonl"
    before = path.read_text()
    case = _cases(datasets)[CASE]
    confirmed = {
        CASE: case.model_copy(update={"label_status": "confirmed", "annotators": ["po", "vk"]})
    }

    def crash(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError, match="disk full"):
        write_cases(datasets, confirmed)
    monkeypatch.undo()
    assert path.read_text() == before
    assert sorted(p.name for p in path.parent.iterdir()) == [
        "dev.jsonl",
        "heldout.jsonl",
        "validation.jsonl",
    ]

    assert write_cases(datasets, confirmed) == 1
    assert _cases(datasets)[CASE].label_status == "confirmed"
    assert not [p for p in path.parent.iterdir() if p.name.startswith(".")]


def test_write_cases_keeps_a_symlinked_case_file_a_symlink(datasets: Path, tmp_path: Path) -> None:
    path = datasets / "prompt_injection" / "dev.jsonl"
    real = tmp_path / "real-dev.jsonl"
    shutil.move(path, real)
    path.symlink_to(real)
    case = _cases(datasets)[CASE]
    assert write_cases(datasets, {CASE: case.model_copy(update={"notes": "updated"})}) == 1
    assert path.is_symlink() and "updated" in real.read_text()
