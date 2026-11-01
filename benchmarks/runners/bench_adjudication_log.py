"""Append to the adjudication log under a lock, so concurrent settles don't interleave.

The lock is `flock` on the log itself, so it is released even if the process dies. Windows has
no `flock`; there the append is unlocked, and two settles must not run on one log at once.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from bench_adjudications import Adjudication, index_adjudications, parse_adjudications
from bench_cases import Case

if sys.platform != "win32":
    import fcntl


def append_adjudication(
    path: Path, entry: Adjudication, cases: dict[str, Case], *, replace: bool = False
) -> Adjudication:
    """Add `entry` to the log at `path`, refusing it if the log would become invalid.

    With `replace`, the entry supersedes the item's current entry, which must exist; without
    it, an item already settled on its current run is refused. Returns the entry as written.
    The log is locked while it is read and appended to, so concurrent settles don't interleave
    (on POSIX only; on Windows, don't run two settles at once).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with _locked(path) as log:
        log.seek(0)
        text = log.read()
        existing = parse_adjudications(path, text)
        current = index_adjudications(existing, cases).settled.get((entry.case_id, entry.key))
        if replace and current is None:
            raise ValueError(f"{entry.describe()} has no current entry to replace")
        if not replace and current is not None:
            raise ValueError(
                f"{entry.describe()} is already settled on this run; pass --replace to "
                "supersede that entry"
            )
        if current is not None:
            entry = entry.model_copy(update={"replaces": current.entry_id})
        index_adjudications([*existing, entry], cases)
        separator = "\n" if text and not text.endswith("\n") else ""
        log.write(separator + entry.to_line() + "\n")
        log.flush()
        os.fsync(log.fileno())
    return entry


@contextmanager
def _locked(path: Path) -> Generator[IO[str]]:
    with path.open("a+", encoding="utf-8") as log:
        if sys.platform != "win32":
            fcntl.flock(log.fileno(), fcntl.LOCK_EX)
        try:
            yield log
        finally:
            if sys.platform != "win32":
                fcntl.flock(log.fileno(), fcntl.LOCK_UN)
