"""Command-line arguments for annotate.py."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import get_args

from bench_adjudications import ADJUDICATIONS_FILE
from bench_annotations import LABELS_DIR, Dimension
from bench_cases import CHECKS, SPLITS
from bench_load import DATASETS_DIR


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Blind double labelling for the benchmark.")
    root.add_argument("--datasets", type=Path, default=DATASETS_DIR, help="case folder")
    root.add_argument("--labels", type=Path, default=LABELS_DIR, help="label files folder")
    commands = root.add_subparsers(dest="command", required=True)

    blank = commands.add_parser("template", help="write blank label files for one annotator")
    blank.add_argument("annotator")
    blank.add_argument("--check", choices=CHECKS, action="append", default=None)
    blank.add_argument("--split", choices=SPLITS, default="dev")

    compare = commands.add_parser("agreement", help="agreement and kappa between two annotators")
    compare.add_argument("first")
    compare.add_argument("second")
    compare.add_argument("--json", action="store_true", help="print the report as JSON")

    settle = commands.add_parser("settle", help="record how one disagreement was settled")
    settle.add_argument("case_id")
    settle.add_argument("dimension", choices=get_args(Dimension))
    settle.add_argument("subject", help="the claim text, 'step N', or 'run'")
    settle.add_argument("label", help="the settled label")
    settle.add_argument("--how", choices=("discussion", "owner_ruling"), required=True)
    settle.add_argument("--by", nargs="+", required=True, help="who decided")
    settle.add_argument("--reason", required=True)
    settle.add_argument("--ruling", help="the rulings-log entry an owner ruling follows")
    settle.add_argument("--adjudications", type=Path, default=ADJUDICATIONS_FILE)

    confirm = commands.add_parser("merge", help="confirm cases whose labels are settled")
    confirm.add_argument("--adjudications", type=Path, default=ADJUDICATIONS_FILE)
    confirm.add_argument("--write", action="store_true", help="rewrite the case files")
    return root
