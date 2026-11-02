"""The export's `manifest.json`: which dataset revision was exported, from which commit, and
how many cases of each check, split and origin it holds."""

from __future__ import annotations

import subprocess
from collections import Counter

from pydantic import BaseModel, ConfigDict

from bench_cases import CHECKS, SPLITS, Case, CheckName, Split
from bench_leaks import CaseTree
from hf_origins import REPO_ROOT

EXPORT_FORMAT_VERSION = 1
"""Bumped when the exported folder's layout or the case lines' format changes."""

Counts = dict[CheckName, dict[Split, dict[str, int]]]


class Manifest(BaseModel):
    """Everything the dataset card is generated from, also written as `manifest.json`."""

    model_config = ConfigDict(extra="forbid")

    format_version: int = EXPORT_FORMAT_VERSION
    dataset_version: str
    attest_commit: str | None
    hf_repo: str
    counts: Counts
    """Cases per check, split and origin. Every check and split is listed, even when empty."""
    label_status: dict[str, int]

    def check_total(self, check: CheckName) -> int:
        return sum(sum(by_origin.values()) for by_origin in self.counts[check].values())

    def split_total(self, check: CheckName, split: Split) -> int:
        return sum(self.counts[check][split].values())

    def total(self) -> int:
        return sum(self.check_total(check) for check in CHECKS)

    def origins(self) -> list[str]:
        return sorted(
            {
                origin
                for by_split in self.counts.values()
                for by_origin in by_split.values()
                for origin in by_origin
            }
        )

    def origin_split_total(self, origin: str, split: Split) -> int:
        return sum(self.counts[check][split].get(origin, 0) for check in CHECKS)

    def data_file(self, check: CheckName, split: Split) -> str | None:
        """The split's file path in the export, or None when the split has no cases."""
        if self.split_total(check, split) == 0:
            return None
        return f"data/{check}/{split}.jsonl"


def count_cases(cases: CaseTree) -> Counts:
    return {
        check: {
            split: dict(sorted(Counter(case.origin for case in cases[check][split]).items()))
            for split in SPLITS
        }
        for check in CHECKS
    }


def count_label_status(cases: CaseTree) -> dict[str, int]:
    found: Counter[str] = Counter({"draft": 0, "confirmed": 0})
    for case in _all(cases):
        found[case.label_status] += 1
    return dict(sorted(found.items()))


def git_commit() -> str | None:
    """The attest commit checked out, or None outside a git checkout."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def _all(cases: CaseTree) -> list[Case]:
    return [case for by_split in cases.values() for split in by_split.values() for case in split]
