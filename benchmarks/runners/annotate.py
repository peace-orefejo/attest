"""Blind double labelling for the benchmark: label templates, agreement, and merging.

    uv run python benchmarks/runners/annotate.py template po --check faithfulness
    uv run python benchmarks/runners/annotate.py agreement po vk
    uv run python benchmarks/runners/annotate.py merge            # dry run
    uv run python benchmarks/runners/annotate.py merge --write    # confirm the settled cases

Each annotator fills in their own `<labels>/<annotator>/<case id>.json` files. Blindness is a
procedure, not something this tool enforces: don't open anyone else's label files, the case
files' draft labels, or attest's output until your own labels are done.

For a private dataset (`--datasets` anywhere but benchmarks/datasets), pass `--labels` (and, for
merge, `--adjudications`) outside this repository or under benchmarks/private/: label files copy
the runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bench_agreement import agreement, markdown
from bench_annotations import ANNOTATOR_PATTERN, LABELS_DIR, AnnotationError, run_sha256
from bench_annotations import template as label_template
from bench_cases import CHECKS, SPLITS
from bench_label_files import load_annotations
from bench_load import DATASETS_DIR, DatasetError, Datasets, load_datasets
from bench_merge import ADJUDICATIONS_FILE, load_adjudications, merge
from bench_write import write_cases

REPO_DIR = DATASETS_DIR.parent.parent
PRIVATE_DIR = DATASETS_DIR.parent / "private"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blind double labelling for the benchmark.")
    parser.add_argument("--datasets", type=Path, default=DATASETS_DIR, help="case folder")
    parser.add_argument("--labels", type=Path, default=LABELS_DIR, help="label files folder")
    commands = parser.add_subparsers(dest="command", required=True)

    blank = commands.add_parser("template", help="write blank label files for one annotator")
    blank.add_argument("annotator")
    blank.add_argument("--check", choices=CHECKS, action="append", default=None)
    blank.add_argument("--split", choices=SPLITS, default="dev")

    compare = commands.add_parser("agreement", help="agreement and kappa between two annotators")
    compare.add_argument("first")
    compare.add_argument("second")
    compare.add_argument("--json", action="store_true", help="print the report as JSON")

    confirm = commands.add_parser("merge", help="confirm cases whose labels are settled")
    confirm.add_argument("--adjudications", type=Path, default=ADJUDICATIONS_FILE)
    confirm.add_argument("--write", action="store_true", help="rewrite the case files")

    args = parser.parse_args(argv)
    private = args.datasets.resolve() != DATASETS_DIR.resolve()
    if private:
        paths = [args.labels] + ([args.adjudications] if args.command == "merge" else [])
        exposed = [str(path) for path in paths if _inside_repo(path)]
        if exposed:
            parser.error(
                f"--datasets is private, so keep its labels out of this repository: "
                f"{', '.join(exposed)} is inside it. Pass --labels (and --adjudications) "
                f"outside the repository or under {PRIVATE_DIR}"
            )
    if args.command == "agreement" and args.first == args.second:
        parser.error("compare two different annotators")
    try:
        datasets = load_datasets(args.datasets, allow_missing=private)
        cases = {
            case.id: case
            for by_split in datasets.cases.values()
            for split_cases in by_split.values()
            for case in split_cases
        }
        if args.command == "template":
            return _template(args, datasets, parser)
        loaded = load_annotations(args.labels, cases)
        annotations = loaded.annotations
        if loaded.unfinished:
            print(
                f"skipping {len(loaded.unfinished)} unfinished label file(s), such as "
                f"{loaded.unfinished[0]}",
                file=sys.stderr,
            )
        for stale in loaded.stale:
            print(
                f"skipping stale {stale.path}: {stale.reason}; delete it and run template again",
                file=sys.stderr,
            )
        if args.command == "agreement":
            report = agreement(annotations, cases, args.first, args.second)
            print(report.model_dump_json(indent=2) if args.json else markdown(report), end="")
            return 0
        outcome = merge(annotations, cases, load_adjudications(args.adjudications))
    except (DatasetError, AnnotationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for case_id, reasons in outcome.unresolved.items():
        print(f"not confirmed  {case_id}: {'; '.join(reasons)}")
    for case_id in outcome.confirmed:
        print(f"confirmed      {case_id}")
    if args.write:
        written = write_cases(args.datasets, outcome.confirmed)
        print(f"\nwrote {written} confirmed case(s) to {args.datasets}")
    elif outcome.confirmed:
        print("\ndry run: pass --write to update the case files")
    return 0


def _template(
    args: argparse.Namespace,
    datasets: Datasets,
    parser: argparse.ArgumentParser,
) -> int:
    if not ANNOTATOR_PATTERN.fullmatch(args.annotator):
        parser.error("annotator names are lowercase initials or ids, such as 'po'")
    folder: Path = args.labels / args.annotator
    folder.mkdir(parents=True, exist_ok=True)
    written = kept = 0
    stale: list[Path] = []
    for check in args.check or CHECKS:
        for case in datasets.split(check, args.split):
            path = folder / f"{case.id}.json"
            if path.exists():
                kept += 1
                if _written_for(path) != run_sha256(case):
                    stale.append(path)
                continue
            path.write_text(json.dumps(label_template(case), indent=2) + "\n", encoding="utf-8")
            written += 1
    print(f"wrote {written} blank label file(s) to {folder}; kept {kept} already there")
    for path in stale:
        print(f"stale: {path} is for an older version of its run; delete it and run again")
    return 0


def _written_for(path: Path) -> object:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return raw.get("run_sha256") if isinstance(raw, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]


def _inside_repo(path: Path) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(REPO_DIR) and not resolved.is_relative_to(PRIVATE_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
