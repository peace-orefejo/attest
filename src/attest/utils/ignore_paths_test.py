"""Splitting paths for matching: separators, `.` and `..`, and paths whose root is unknown."""

import pytest

from attest.utils.ignore_paths import PathParts, normalize_path, split_path


@pytest.mark.parametrize(
    ("path", "parts", "floating"),
    [
        ("secrets/k.env", ("secrets", "k.env"), False),
        ("./secrets//k.env", ("secrets", "k.env"), False),
        ("secrets\\k.env", ("secrets", "k.env"), False),
        ("src/../secrets/k.env", ("secrets", "k.env"), False),
        ("src/a/../../secrets/./k.env", ("secrets", "k.env"), False),
        ("../secrets/k.env", ("secrets", "k.env"), True),
        ("src/../../secrets/k.env", ("secrets", "k.env"), True),
        ("/home/u/repo/secrets/k.env", ("home", "u", "repo", "secrets", "k.env"), True),
        ("C:\\repo\\k.env", ("C:", "repo", "k.env"), True),
        ("c:", ("c:",), True),
        ("", (), False),
    ],
)
def test_split_path(path, parts, floating):
    assert split_path(path) == PathParts(parts=parts, floating=floating)


def test_normalize_path_joins_the_resolved_segments():
    assert normalize_path("/a/./b/../c\\d") == "a/c/d"
