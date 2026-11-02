"""Build the Hugging Face export folder from the public benchmark datasets.

Only the public datasets under `DATASETS_DIR` are exported, loaded through `load_datasets()` so
every layout, leak and seed-origin rule holds. Private datasets are never read: there is no way
to pass another root.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from bench_cases import CHECKS, SPLITS, Case, CheckName, Split
from bench_load import DATASETS_DIR, case_files, load_datasets
from hf_card import render_card
from hf_manifest import Manifest, count_cases, count_label_status, git_commit
from hf_origins import BENCHMARKS_DIR, ORIGINS, licence_name, notice_name

DEFAULT_OUT = BENCHMARKS_DIR / "hf-build"
DEFAULT_REPO = "pandorasBoxee/attest-benchmark"
MANIFEST = "manifest.json"
_PROTECTED = (DATASETS_DIR, BENCHMARKS_DIR / "private", BENCHMARKS_DIR / "sources")


class ExportError(ValueError):
    """The export can't be built or uploaded as asked."""


def build(out: Path = DEFAULT_OUT, *, repo: str = DEFAULT_REPO) -> Manifest:
    """Write the dataset folder to `out`, replacing an earlier export there, and return its
    manifest. The output depends only on the public datasets, the licence files and the attest
    commit, so two builds of the same checkout are byte-identical."""
    _check_out(out)
    lines, manifest = public_export(repo=repo)
    if out.exists():
        shutil.rmtree(out)
    for (check, split), split_lines in lines.items():
        if split_lines:
            _write(out / "data" / check / f"{split}.jsonl", "".join(f"{x}\n" for x in split_lines))
    _write_licences(out, manifest.origins())
    _write(out / "README.md", render_card(manifest))
    _write(out / MANIFEST, json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n")
    return manifest


def public_export(
    root: Path = DATASETS_DIR, *, repo: str = DEFAULT_REPO
) -> tuple[dict[tuple[CheckName, Split], list[str]], Manifest]:
    """Every public case line, by check and split, and the manifest describing them.

    `root` exists only so a caller can't silently export another folder: anything but the
    public datasets is refused."""
    if root.resolve() != DATASETS_DIR.resolve():
        raise ExportError(f"{root}: only the public datasets ({DATASETS_DIR}) can be exported")
    datasets = load_datasets()
    lines: dict[tuple[CheckName, Split], list[str]] = {
        (check, split): stored_lines(datasets.split(check, split), check, split)
        for check in CHECKS
        for split in SPLITS
    }
    unknown = sorted({c.origin for by in datasets.cases.values() for s in by.values() for c in s})
    missing = [origin for origin in unknown if origin not in ORIGINS]
    if missing:
        raise ExportError(f"no licence or provenance recorded in hf_origins for: {missing}")
    manifest = Manifest(
        dataset_version=datasets.version,
        attest_commit=git_commit(),
        hf_repo=repo,
        counts=count_cases(datasets.cases),
        label_status=count_label_status(datasets.cases),
    )
    return lines, manifest


def stored_lines(cases: list[Case], check: CheckName, split: Split) -> list[str]:
    """The split's case lines exactly as stored, in the loader's order (the split's own file,
    then each `<split>-<origin>.jsonl` by name). Fails if they don't match what was loaded."""
    lines = [
        line.strip()
        for path in case_files(DATASETS_DIR, check, split)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stored_ids = [json.loads(line)["id"] for line in lines]
    if stored_ids != [case.id for case in cases]:
        raise ExportError(f"{check}/{split}: case files changed while exporting; build again")
    return lines


def _check_out(out: Path) -> None:
    resolved = out.resolve()
    for protected in _PROTECTED:
        if resolved == protected.resolve() or resolved.is_relative_to(protected.resolve()):
            raise ExportError(f"{out}: refusing to write the export inside {protected}")
    if resolved.is_dir() and any(resolved.iterdir()) and not (resolved / MANIFEST).is_file():
        raise ExportError(
            f"{out}: folder exists and isn't an earlier export (no {MANIFEST}); "
            "choose an empty or new folder"
        )
    if resolved.exists() and not resolved.is_dir():
        raise ExportError(f"{out}: not a folder")


def _write_licences(out: Path, origins: list[str]) -> None:
    for origin in origins:
        info = ORIGINS[origin]
        _copy(info.licence_file, out / "LICENSES" / licence_name(origin))
        if info.notice_file is not None:
            _copy(info.notice_file, out / "LICENSES" / notice_name(origin))


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
