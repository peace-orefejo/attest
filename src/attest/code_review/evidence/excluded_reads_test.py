"""Checking grep output against exclusions stays bounded, even when file content is hostile."""

import time

import pytest

from attest import Exclusions
from attest.code_review import FileRead
from attest.code_review.evidence.excluded_reads import MAX_GREP_CHECK_SEGMENTS, hide_read
from attest.exclusions import MAX_PATH_CHARS

GLOBS = Exclusions(
    patterns=tuple([f"*.ext{i}" for i in range(25)] + [f"**/d{i}*/**/*.y{i}" for i in range(25)])
)

PEM = Exclusions(patterns=("*.pem",))


def _grep(output: str) -> FileRead:
    return FileRead(tool="grep", arguments={"pattern": "x"}, output=output)


def test_hostile_grep_lines_are_checked_in_bounded_time():
    # Each line offers eight deep candidate paths drawn from file content; the old matcher
    # took seconds per line. They stay under the 1,024 segments past which a candidate is
    # excluded.
    content = ":".join("d1/" * 100 for _ in range(10))
    shorter = ":".join("d1/" * 100 for _ in range(7))
    lines = [f"src/app{i}.py:{i}:{content}" for i in range(200)]
    lines += [f"/{'d1/' * 300}:{i}:{shorter}" for i in range(50)]
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
    assert hidden.cut
    assert hide_read(hidden.read, GLOBS).cut


def test_a_small_grep_is_kept_whole():
    read = _grep("src/a.py:1:x\nsrc/b.py-2-y")
    hidden = hide_read(read, GLOBS)
    assert hidden.read == read
    assert not hidden.cut


def test_a_grep_line_deeper_than_any_real_path_is_withheld():
    deep = "/".join(["d"] * 1030) + "/k.pem"
    hidden = hide_read(_grep(f"src/a.py:1:x\n{deep}:1:KEY=1"), PEM)
    assert hidden.excluded == [deep]
    assert "KEY=1" not in hidden.read.output


@pytest.mark.parametrize("path", ["secrets/a\nb.env", "notes\r.txt", "x" * (MAX_PATH_CHARS + 1)])
def test_a_read_argument_that_cannot_be_checked_counts_as_excluded(path):
    read = FileRead(arguments={"path": path}, output="TOKEN=1")
    hidden = hide_read(read, PEM)
    assert len(hidden.excluded) == 1
    assert "\n" not in hidden.excluded[0] and len(hidden.excluded[0]) < 300
    assert "TOKEN" not in hidden.read.output


def test_the_search_text_and_empty_arguments_are_not_paths():
    read = FileRead(arguments={"pattern": "a\nb", "path": ""}, output="ok")
    assert hide_read(read, PEM).read == read


def test_a_grep_line_whose_text_only_mentions_an_excluded_file_is_flagged():
    hidden = hide_read(_grep("src/config.py:3:# see x.pem\nsrc/ok.py:1:y"), PEM)
    assert hidden.excluded == ["src/config.py:3:# see x.pem"]
    assert hidden.named_only == hidden.excluded
    direct = hide_read(_grep("certs/k.pem:1:KEY\nC:\\repo\\k.pem:1:KEY"), PEM)
    assert direct.excluded == ["certs/k.pem", "C:\\repo\\k.pem"]
    assert direct.named_only == []
