"""Exclusions fail closed: case and Unicode variants, odd path forms and absurd paths."""

import unicodedata

import pytest

from attest import Exclusions
from attest.exclusions import MAX_PATH_CHARS, MAX_PATH_DEPTH

SECRETS = Exclusions(patterns=("secrets/", "café.env", "/Private/"))


@pytest.mark.parametrize(
    "path",
    [
        "Secrets/k.env",
        "SECRETS/k.env",
        "app/Secrets/k.env",
        unicodedata.normalize("NFD", "café.env"),
        "CAFÉ.ENV",
        "private/notes.md",
        "PRIVATE/notes.md",
        "secrets./k.env",
        "café.env ",
    ],
)
def test_case_unicode_and_trailing_dot_variants_are_excluded(path):
    assert SECRETS.excludes(path)


def test_a_negation_only_re_includes_what_both_forms_re_include():
    exclusions = Exclusions(patterns=("*.env", "!Keep.env"))
    assert not exclusions.excludes("Keep.env")
    assert exclusions.excludes("keep.env")


def test_unrelated_paths_stay_included():
    assert SECRETS.excluded(["app/main.py", "docs/secret.md", "cafe.env"]) == []


@pytest.mark.parametrize(
    "path",
    [
        "/home/u/repo/secrets/k.env",
        "src/../secrets/k.env",
        "../../secrets/k.env",
        "D:\\work\\repo\\private\\notes.md",
    ],
)
def test_path_forms_are_normalized_before_matching(path):
    assert SECRETS.excludes(path)


def test_paths_longer_or_deeper_than_any_real_file_are_excluded():
    assert SECRETS.excludes("a" * (MAX_PATH_CHARS + 1))
    assert SECRETS.excludes("/".join(["a"] * (MAX_PATH_DEPTH + 1)))
    assert not SECRETS.excludes("/".join(["a"] * MAX_PATH_DEPTH))


def test_without_patterns_nothing_is_excluded_however_long():
    assert not Exclusions().excludes("a" * (MAX_PATH_CHARS + 1))
