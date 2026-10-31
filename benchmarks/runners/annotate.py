"""Blind double labelling for the benchmark: label templates, agreement, settling and merging.

    uv run python benchmarks/runners/annotate.py template po --check faithfulness
    uv run python benchmarks/runners/annotate.py agreement po vk
    uv run python benchmarks/runners/annotate.py settle inj-clean-output label run none \\
        --how discussion --by po vk --reason "the output only has data"
    uv run python benchmarks/runners/annotate.py merge            # dry run
    uv run python benchmarks/runners/annotate.py merge --write    # confirm the settled cases

Each annotator fills in their own `<labels>/<annotator>/<case id>.json` files. Blindness is a
procedure, not something this tool enforces: don't open anyone else's label files, the case
files' draft labels, or attest's output until your own labels are done.

For a private dataset (`--datasets` anywhere but benchmarks/datasets), pass `--labels` and
`--adjudications` outside this repository or under benchmarks/private/: label files copy the
runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bench_adjudications import Adjudication, append_adjudication, load_adjudications
from bench_agreement import agreement, markdown
from bench_annotate_args import parser as annotate_parser
from bench_annotations import ANNOTATOR_PATTERN, AnnotationError, run_sha256
from bench_cases import CHECKS, Case
from bench_label_files import load_annotations
from bench_load import DATASETS_DIR, DatasetError, load_datasets
from bench_merge import merge
from bench_template import write_templates
from bench_write import write_cases

REPO_DIR = DATASETS_DIR.parent.parent
PRIVATE_DIR = DATASETS_DIR.parent / "private"
USES_LOG = ("merge", "settle")


def main(argv: list[str] | None = None) -> int:
    parser = annotate_parser()
    args = parser.parse_args(argv)
    private = args.datasets.resolve() != DATASETS_DIR.resolve()
    if private:
        paths = [args.labels] + ([args.adjudications] if args.command in USES_LOG else [])
        exposed = [str(path) for path in paths if _inside_repo(path)]
        if exposed:
            parser.error(
                f"--datasets is private, so keep its labels out of this repository: "
                f"{', '.join(exposed)} is inside it. Pass --labels and --adjudications "
                f"outside the repository or under {PRIVATE_DIR}"
            )
    if args.command == "agreement" and args.first == args.second:
        parser.error("compare two different annotators")
    if args.command == "template" and not ANNOTATOR_PATTERN.fullmatch(args.annotator):
        parser.error("annotator names are lowercase initials or ids, such as 'po'")
    try:
        datasets = load_datasets(args.datasets, allow_missing=private)
        if args.command == "template":
            cases = [c for check in args.check or CHECKS for c in datasets.split(check, args.split)]
            return _template(args.labels / args.annotator, cases, private=private)
        cases = {
            case.id: case
            for by_split in datasets.cases.values()
            for split_cases in by_split.values()
            for case in split_cases
        }
        if args.command == "settle":
            return _settle(args, cases)
        return _labelled(args, cases)
    except (DatasetError, AnnotationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _template(folder: Path, cases: list[Case], *, private: bool) -> int:
    result = write_templates(folder, cases, forbidden=_inside_repo if private else None)
    print(f"wrote {result.written} blank label file(s) to {folder}; kept {result.kept} there")
    for stale in result.stale:
        print(f"stale: {stale.path}: {stale.reason}; delete it and run again")
    return 0


def _settle(args: argparse.Namespace, cases: dict[str, Case]) -> int:
    case = cases.get(args.case_id)
    if case is None:
        raise AnnotationError(f"{args.case_id}: no such case")
    entry = Adjudication(
        case_id=case.id,
        dimension=args.dimension,
        subject=args.subject,
        label=args.label,
        how=args.how,
        decided_by=args.by,
        reason=args.reason,
        ruling=args.ruling,
        run_sha256=run_sha256(case),
    )
    append_adjudication(args.adjudications, entry, cases)
    print(f"settled {entry.describe()} as {entry.label!r} in {args.adjudications}")
    return 0


def _labelled(args: argparse.Namespace, cases: dict[str, Case]) -> int:
    loaded = load_annotations(args.labels, cases)
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
        report = agreement(loaded.annotations, cases, args.first, args.second)
        print(report.model_dump_json(indent=2) if args.json else markdown(report), end="")
        return 0
    outcome = merge(loaded.annotations, cases, load_adjudications(args.adjudications))
    for x in outcome.stale_adjudications:
        print(
            f"skipping stale adjudication of {x.describe()}: the run changed after it was "
            f"settled; settle it again",
            file=sys.stderr,
        )
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


def _inside_repo(path: Path) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(REPO_DIR) and not resolved.is_relative_to(PRIVATE_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
