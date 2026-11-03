"""Checking grep output against exclusions stays bounded, even when file content is hostile."""

import time

from attest import Exclusions
from attest.code_review import FileRead
from attest.code_review.evidence.excluded_reads import MAX_GREP_CHECK_SEGMENTS, hide_read

GLOBS = Exclusions(
    patterns=tuple([f"*.ext{i}" for i in range(25)] + [f"**/d{i}*/**/*.y{i}" for i in range(25)])
)


def _grep(output: str) -> FileRead:
    return FileRead(tool="grep", arguments={"pattern": "x"}, output=output)


def test_hostile_grep_lines_are_checked_in_bounded_time():
    # Each line offers eight deep candidate paths drawn from file content; the old matcher
    # took seconds per line.
    content = ":".join("d1/" * 100 for _ in range(12))
    lines = [f"src/app{i}.py:{i}:{content}" for i in range(200)]
    lines += [f"/{'d1/' * 300}:{i}:{content}" for i in range(50)]
    started = time.perf_counter()
    hidden = hide_read(_grep("\n".join(lines)), GLOBS)
    assert time.perf_counter() - started < 5
    assert hidden.excluded == []


def test_a_grep_too_large_to_check_keeps_only_the_checked_lines():
    line = "src/" + "a/" * 99 + "x.py:1:TOKEN"
    lines = [line.replace("x.py", f"x{i}.py") for i in range(MAX_GREP_CHECK_SEGMENTS // 100)]
    hidden = hide_read(_grep("\n".join(lines)), GLOBS)
    kept = hidden.read.output.split("\n")
    assert 0 < len(kept) - 1 < len(lines)
    assert kept[:-1] == lines[: len(kept) - 1]
    assert kept[-1].startswith(f"[grep output cut after {len(kept) - 1} lines")
    assert hidden.excluded == []


def test_a_small_grep_is_kept_whole():
    read = _grep("src/a.py:1:x\nsrc/b.py-2-y")
    assert hide_read(read, GLOBS).read == read
