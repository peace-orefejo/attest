from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from bench_cases import CHECKS, SPLITS, Case
from bench_load import DATASETS_DIR, case_files, load_datasets
from hf_build import MANIFEST, ExportError, build, public_export
from hf_card import front_matter, render_card
from hf_card_text import OPEN_QUESTIONS
from hf_manifest import Manifest
from hf_origins import BENCHMARKS_DIR, ORIGINS, REPO_ROOT, licence_name, notice_name


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("hf") / "export"
    build(out)
    return out


def _files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def _card_header(folder: Path) -> dict[str, Any]:
    text = (folder / "README.md").read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None
    header = yaml.safe_load(match.group(1))
    assert isinstance(header, dict)
    return header


def test_build_is_byte_identical_twice(built: Path, tmp_path: Path) -> None:
    again = tmp_path / "again"
    build(again)
    assert _files(again) == _files(built)
    build(again)  # rebuilding over an earlier export replaces it
    assert _files(again) == _files(built)


def test_every_line_is_a_stored_case_and_counts_match_the_loader(built: Path) -> None:
    datasets = load_datasets()
    for check in CHECKS:
        for split in SPLITS:
            path = built / "data" / check / f"{split}.jsonl"
            expected = datasets.split(check, split)
            if not expected:
                assert not path.exists()
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            cases = [Case.model_validate_json(line) for line in lines]
            assert [case.id for case in cases] == [case.id for case in expected]
            assert cases == expected
            stored = [
                json.loads(line)
                for file in case_files(DATASETS_DIR, check, split)
                for line in file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert [json.loads(line) for line in lines] == stored


def test_manifest_matches_the_public_datasets(built: Path) -> None:
    datasets = load_datasets()
    manifest = Manifest.model_validate_json((built / MANIFEST).read_text(encoding="utf-8"))
    assert manifest.dataset_version == datasets.version
    for check in CHECKS:
        for split in SPLITS:
            assert manifest.split_total(check, split) == len(datasets.split(check, split))
            for origin, count in manifest.counts[check][split].items():
                found = [c for c in datasets.split(check, split) if c.origin == origin]
                assert len(found) == count
    assert sum(manifest.label_status.values()) == manifest.total()
    assert manifest.dataset_version in (built / "README.md").read_text(encoding="utf-8")


def test_export_reloads_with_attests_loader(built: Path) -> None:
    exported = load_datasets(built / "data", allow_missing=True)
    public = load_datasets()
    for check in CHECKS:
        for split in SPLITS:
            assert exported.split(check, split) == public.split(check, split)


def test_card_yaml_parses_and_lists_exactly_the_data_files(built: Path) -> None:
    header = _card_header(built)
    assert header["license"] == ["cc-by-4.0", "mit", "apache-2.0"]
    assert "license_name" not in header
    listed = {entry["path"] for config in header["configs"] for entry in config["data_files"]}
    existing = {name for name in _files(built) if name.startswith("data/")}
    assert listed == existing
    for config in header["configs"]:
        for entry in config["data_files"]:
            assert entry["path"] == f"data/{config['config_name']}/{entry['split']}.jsonl"


def test_front_matter_stays_valid_for_empty_checks_and_splits() -> None:
    counts = {check: {split: {} for split in SPLITS} for check in CHECKS}
    counts["tool_use"]["dev"] = {"attest-seed": 2}
    manifest = Manifest.model_validate(
        {
            "dataset_version": "0" * 64,
            "attest_commit": None,
            "hf_repo": "someone/attest-benchmark",
            "counts": counts,
            "label_status": {"confirmed": 0, "draft": 2},
        }
    )
    header = yaml.safe_load(front_matter(manifest))
    assert header["configs"] == [
        {
            "config_name": "tool_use",
            "data_files": [{"split": "dev", "path": "data/tool_use/dev.jsonl"}],
        }
    ]
    assert "someone/attest-benchmark" in render_card(manifest)


def test_licences_and_notices_are_copied_verbatim(built: Path) -> None:
    manifest = Manifest.model_validate_json((built / MANIFEST).read_text(encoding="utf-8"))
    assert manifest.origins() == sorted(ORIGINS)
    for origin in manifest.origins():
        info = ORIGINS[origin]
        assert (
            built / "LICENSES" / licence_name(origin)
        ).read_bytes() == info.licence_file.read_bytes()
        if info.notice_file is not None:
            notice = built / "LICENSES" / notice_name(origin)
            assert notice.read_bytes() == info.notice_file.read_bytes()
    seed = (built / "LICENSES" / "attest-seed.txt").read_bytes()
    assert seed == (DATASETS_DIR / "LICENSE").read_bytes()
    assert seed != (REPO_ROOT / "LICENSE").read_bytes()
    assert b"CC-BY-4.0" in seed
    assert b"https://creativecommons.org/licenses/by/4.0/" in seed
    assert (built / "LICENSES" / "toolbench-NOTICE.txt").is_file()


def test_card_licences_labels_cc_by_and_upstream_runs_under_their_own(built: Path) -> None:
    card = (built / "README.md").read_text(encoding="utf-8")
    licences = card.split('<a id="licenses"></a>', 1)[1].split("## Citation", 1)[0]
    assert "AGPL" not in card
    assert "labels, notes and conversion work on every case" in licences
    assert "keeps its upstream licence (Apache-2.0, MIT)" in licences
    assert licences.count("- Labels, notes and conversion: CC-BY-4.0") == 3
    assert "- Upstream run content: MIT, full text in `LICENSES/tau-bench.txt`" in licences
    assert "- Upstream run content: Apache-2.0, full text in `LICENSES/toolbench.txt`" in licences
    assert "- Licence: CC-BY-4.0, see `LICENSES/attest-seed.txt`" in licences


def test_card_licence_list_holds_only_the_licences_present() -> None:
    counts = {check: {split: {} for split in SPLITS} for check in CHECKS}
    counts["tool_use"]["dev"] = {"attest-seed": 2, "agentdojo": 1}
    manifest = Manifest.model_validate(
        {
            "dataset_version": "0" * 64,
            "attest_commit": None,
            "hf_repo": "someone/attest-benchmark",
            "counts": counts,
            "label_status": {"confirmed": 0, "draft": 3},
        }
    )
    assert yaml.safe_load(front_matter(manifest))["license"] == ["cc-by-4.0", "mit"]


def test_build_reads_only_public_files_never_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched: list[Path] = []
    for name in ("open", "iterdir"):
        original: Callable[..., object] = getattr(pathlib.Path, name)

        def spy(
            self: Path, *args: object, _original: Callable[..., object] = original, **kw: object
        ) -> object:
            touched.append(self.resolve())
            return _original(self, *args, **kw)

        monkeypatch.setattr(pathlib.Path, name, spy)
    out = tmp_path / "export"
    build(out)
    allowed = (DATASETS_DIR.resolve(), (BENCHMARKS_DIR / "sources").resolve(), out.resolve())
    assert (DATASETS_DIR / "tool_use" / "dev.jsonl").resolve() in touched
    assert all(any(p.is_relative_to(root) for root in allowed) for p in touched), touched
    assert not any(p.is_relative_to((BENCHMARKS_DIR / "private").resolve()) for p in touched)


@pytest.mark.parametrize("root", [BENCHMARKS_DIR / "private", Path("elsewhere")])
def test_export_refuses_any_root_but_the_public_datasets(root: Path) -> None:
    with pytest.raises(ExportError, match="only the public datasets"):
        public_export(root)


def test_build_refuses_unsafe_output_folders(tmp_path: Path) -> None:
    for inside in (
        DATASETS_DIR / "x",
        BENCHMARKS_DIR / "private" / "x",
        BENCHMARKS_DIR / "sources",
    ):
        with pytest.raises(ExportError, match="refusing to write"):
            build(inside)
    (tmp_path / "keep.txt").write_text("mine")
    with pytest.raises(ExportError, match="isn't an earlier export"):
        build(tmp_path)
    assert (tmp_path / "keep.txt").read_text() == "mine"


def test_origins_match_their_source_files() -> None:
    for origin, info in ORIGINS.items():
        assert info.licence_file.is_file()
        if info.upstream_commit is not None:
            source = (BENCHMARKS_DIR / "sources" / origin / "SOURCE.md").read_text(encoding="utf-8")
            assert info.upstream_commit in source
    assert ORIGINS["attest-seed"].licence == "CC-BY-4.0"
    assert ORIGINS["attest-seed"].licence_file == DATASETS_DIR / "LICENSE"
    assert "CC-BY-4.0" in (DATASETS_DIR / "LICENSE").read_text(encoding="utf-8")


def test_card_lists_every_open_guideline_question() -> None:
    guidelines = (BENCHMARKS_DIR / "annotations" / "guidelines.md").read_text(encoding="utf-8")
    rulings = [
        line
        for line in guidelines.splitlines()
        if "**(open)**" in line and not line.startswith(">")
    ]
    assert len(rulings) == len(OPEN_QUESTIONS)
