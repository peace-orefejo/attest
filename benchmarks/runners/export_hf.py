"""Export the public benchmark cases as a Hugging Face dataset, and upload it.

    uv run python benchmarks/runners/export_hf.py build [--out DIR] [--repo USER/NAME]
    uv run --group hf python benchmarks/runners/export_hf.py upload --repo USER/NAME \\
        [--private] [--dir DIR]

`build` writes the dataset folder (default benchmarks/hf-build/): one JSONL file per check and
split, a generated dataset card, the licences and a manifest. Only the public datasets are
exported; private datasets are never read. `upload` needs `uv sync --group hf` and a token from
`hf auth login` (or HF_TOKEN). It refuses a missing or stale build, creates the dataset repo if
needed, uploads the folder and tags the revision `dv-<dataset_version[:12]>`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bench_cases import CHECKS, SPLITS
from bench_load import DatasetError
from hf_build import DEFAULT_OUT, DEFAULT_REPO, ExportError, build
from hf_manifest import Manifest
from hf_upload import upload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build", help="write the dataset folder")
    build_cmd.add_argument("--out", type=Path, default=DEFAULT_OUT)
    build_cmd.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"the Hub repo the card's examples name (default {DEFAULT_REPO})",
    )
    upload_cmd = commands.add_parser("upload", help="upload a built folder to the Hub")
    upload_cmd.add_argument("--repo", required=True, help="dataset repo, <user>/<name>")
    upload_cmd.add_argument("--private", action="store_true", help="create the repo private")
    upload_cmd.add_argument("--dir", type=Path, default=DEFAULT_OUT, help="the built folder")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            out: Path = args.out
            manifest = build(out, repo=args.repo)
            print(f"wrote {out}\n{summary(manifest)}")
        else:
            print(upload(args.repo, args.dir, private=args.private))
    except (ExportError, DatasetError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def summary(manifest: Manifest) -> str:
    statuses = ", ".join(f"{status} {n}" for status, n in manifest.label_status.items())
    lines = [
        f"dataset_version {manifest.dataset_version}",
        f"attest commit {manifest.attest_commit or 'unknown'}",
        f"{manifest.total()} cases ({statuses})",
    ]
    for check in CHECKS:
        splits = ", ".join(f"{split} {manifest.split_total(check, split)}" for split in SPLITS)
        lines.append(f"  {check}: {splits}")
    for origin in manifest.origins():
        splits = ", ".join(f"{s} {manifest.origin_split_total(origin, s)}" for s in SPLITS)
        lines.append(f"  origin {origin}: {splits}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
