"""The gitignore-style matcher: globs, `**`, directory patterns, negation and comments."""

import time

import pytest

from attest.utils.ignore_rules import (
    is_ignored,
    normalize_path,
    parse_rule,
    parse_rules,
    parts_ignored,
)


def _ignored(patterns: str, path: str, *, is_dir: bool = False) -> bool:
    return is_ignored(path, parse_rules(patterns.splitlines()), is_dir=is_dir)


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("*.env", ".env", True),
        ("*.env", "config/prod.env", True),
        ("*.env", "config/prod.env.example", False),
        ("secret?.txt", "a/secret1.txt", True),
        ("secret?.txt", "a/secret10.txt", False),
        ("data[0-9].csv", "data7.csv", True),
        ("data[!0-9].csv", "data7.csv", False),
        ("data[^0-9].csv", "datax.csv", True),
        ("*.py", "src/deep/module.py", True),
        ("*", "anything/at/all.txt", True),
    ],
)
def test_globs_match_one_segment_at_any_depth(pattern, path, expected):
    assert _ignored(pattern, path) is expected


def test_a_star_never_crosses_a_slash():
    assert not _ignored("src/*.py", "src/deep/module.py")
    assert _ignored("src/*.py", "src/module.py")


def test_a_slash_anchors_the_pattern_to_the_root():
    assert _ignored("/build.log", "build.log")
    assert not _ignored("/build.log", "sub/build.log")
    assert _ignored("docs/private.md", "docs/private.md")
    assert not _ignored("docs/private.md", "site/docs/private.md")


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("**/fixtures", "fixtures/a.json", True),
        ("**/fixtures", "src/x/fixtures/a.json", True),
        ("data/**", "data/a.csv", True),
        ("data/**", "data/deep/er/a.csv", True),
        ("data/**", "data", False),
        ("a/**/b.txt", "a/b.txt", True),
        ("a/**/b.txt", "a/x/y/b.txt", True),
        ("a/**/b.txt", "c/a/x/b.txt", False),
        ("a/**/**/b.txt", "a/x/b.txt", True),
        ("**", "x/y.txt", True),
        ("a**b", "axxb", True),
    ],
)
def test_double_stars(pattern, path, expected):
    assert _ignored(pattern, path) is expected


def test_a_trailing_slash_matches_directories_only():
    assert _ignored("secrets/", "secrets/key.pem")
    assert _ignored("secrets/", "app/secrets/key.pem")
    assert not _ignored("secrets/", "secrets")
    assert _ignored("secrets/", "secrets", is_dir=True)


def test_a_plain_name_matches_a_file_or_a_directory():
    assert _ignored("vendor", "vendor")
    assert _ignored("vendor", "lib/vendor/x.js")


def test_a_later_negation_re_includes_a_file():
    rules = "*.json\n!package.json\n"
    assert _ignored(rules, "data.json")
    assert not _ignored(rules, "package.json")
    assert _ignored(rules + "package.json\n", "package.json")


def test_negation_cannot_re_include_a_file_inside_an_ignored_directory():
    assert _ignored("secrets/\n!secrets/public.txt\n", "secrets/public.txt")
    assert not _ignored("secrets/*\n!secrets/public.txt\n", "secrets/public.txt")


def test_a_negated_directory_lets_its_files_through():
    assert not _ignored("build/\n!build/\n", "build/out.txt")


def test_comments_blank_lines_and_trailing_spaces_are_ignored():
    rules = parse_rules(["# a comment", "", "   ", "*.log   ", "\r"])
    assert [rule.pattern for rule in rules] == ["*.log"]
    assert is_ignored("x.log", rules)


def test_backslash_escapes_a_leading_hash_or_bang_and_glob_characters():
    assert _ignored("\\#notes.md", "#notes.md")
    assert _ignored("\\!important.txt", "!important.txt")
    assert _ignored("star\\*.txt", "star*.txt")
    assert not _ignored("star\\*.txt", "starry.txt")
    assert _ignored("trailing\\ ", "trailing ")


def test_lines_with_nothing_to_match_are_skipped():
    assert parse_rule("/") is None
    assert parse_rule("!") is None
    assert parse_rule("# x") is None


def test_matching_is_case_sensitive():
    assert not _ignored("*.ENV", "prod.env")


def test_paths_are_normalized():
    assert normalize_path("./a//b\\c.txt") == "a/b/c.txt"
    assert normalize_path("/abs/path") == "abs/path"
    assert normalize_path("src/../secrets/./k.env") == "secrets/k.env"
    assert _ignored("/src/x.py", "./src/x.py")
    assert _ignored("/secrets/", "src/../secrets/k.env")
    assert not _ignored("*", "")
    assert not is_ignored("a.txt", [])


@pytest.mark.parametrize(
    "path",
    [
        "/home/u/repo/fixtures/users.json",
        "C:\\Users\\u\\repo\\fixtures\\users.json",
        "../fixtures/users.json",
        "src/../../fixtures/users.json",
    ],
)
def test_a_path_with_an_unknown_root_matches_anchored_patterns_from_any_segment(path):
    assert _ignored("fixtures/**", path)
    assert _ignored("/fixtures/", path)
    assert not _ignored("/fixtures/", "src/fixtures/users.json")


def test_a_floating_path_is_ignored_when_any_start_ignores_it():
    rules = "/a/*.env\n!/b/a/keep.env\n"
    assert _ignored(rules, "/b/a/keep.env")
    assert not _ignored(rules, "b/a/keep.env")


def test_one_pass_gives_every_parent_directory_its_verdict():
    rules = parse_rules(["deep/", "!x"])
    path = "/".join(["a"] * 50 + ["deep"] + ["b"] * 50 + ["x"])
    assert is_ignored(path, rules)
    assert parts_ignored(path.split("/"), rules, is_dir=False)
    assert not is_ignored(path.replace("deep", "shallow"), rules)


def test_hostile_patterns_match_in_linear_time():
    pattern = "/".join(["**", "*"] * 200) + "/never"
    path = "/".join(["segment"] * 200)
    rules = parse_rules([pattern, "*a*a*a*a*a*a*a*a*a*a*a*b"])
    started = time.perf_counter()
    assert not is_ignored(path + "/" + "a" * 250, rules)
    assert time.perf_counter() - started < 2


@pytest.mark.parametrize("prefix", ["", "/"])
def test_a_deep_path_against_many_glob_rules_is_not_quadratic(prefix):
    # The old matcher re-ran every rule for each parent directory: about 20 s here.
    rules = parse_rules(
        [f"*.ext{i}" for i in range(25)] + [f"**/d{i}*/**/*.y{i}" for i in range(25)]
    )
    path = prefix + "/".join(["d1"] * 2000) + "/file.txt"
    started = time.perf_counter()
    assert not is_ignored(path, rules)
    assert time.perf_counter() - started < 2
