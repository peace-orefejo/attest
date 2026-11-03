"""Loading exclusions: discovery, precedence, and refusing unusable pattern files."""

import pytest

from attest import ExclusionError, Exclusions, load_exclusions
from attest.exclusions import (
    MAX_PATTERN_FILE_BYTES,
    MAX_PATTERNS,
    as_exclusions,
    excluded_note,
)


def test_attestignore_is_read_from_the_current_directory_only_when_discovering(
    tmp_path, monkeypatch
):
    (tmp_path / ".attestignore").write_text("# secrets\nsecrets/\n*.pem\n")
    monkeypatch.chdir(tmp_path)
    found = load_exclusions(discover=True)
    assert found.excludes("secrets/prod.env")
    assert found.excludes("certs/key.pem")
    assert found.sources == (str(tmp_path / ".attestignore"),)
    assert not load_exclusions().active


def test_discovery_without_a_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not load_exclusions(discover=True).active


def test_discovery_can_use_another_root(tmp_path):
    (tmp_path / ".attestignore").write_text("data/\n")
    assert load_exclusions(discover=True, root=tmp_path).excludes("data/big.csv")


def test_file_patterns_come_first_then_direct_ones(tmp_path):
    (tmp_path / ".attestignore").write_text("fixtures/*\n")
    extra = tmp_path / "extra.ignore"
    extra.write_text("!fixtures/keep.json\n*.csv\n")
    exclusions = load_exclusions(
        ["!small.csv", "fixtures/keep.json"], files=[extra], discover=True, root=tmp_path
    )
    assert exclusions.patterns == (
        "fixtures/*",
        "!fixtures/keep.json",
        "*.csv",
        "!small.csv",
        "fixtures/keep.json",
    )
    assert exclusions.excludes("fixtures/other.json")
    assert exclusions.excludes("fixtures/keep.json")
    assert exclusions.excludes("big.csv")
    assert not exclusions.excludes("small.csv")


def test_a_missing_pattern_file_is_an_error_not_ignored(tmp_path):
    with pytest.raises(ExclusionError, match="Could not read exclusion file"):
        load_exclusions(files=[tmp_path / "missing"])


def test_a_directory_named_attestignore_is_an_error(tmp_path):
    (tmp_path / ".attestignore").mkdir()
    with pytest.raises(ExclusionError, match="Could not read exclusion file"):
        load_exclusions(discover=True, root=tmp_path)


def test_a_broken_attestignore_link_is_an_error(tmp_path):
    (tmp_path / ".attestignore").symlink_to(tmp_path / "nowhere")
    with pytest.raises(ExclusionError, match="Could not read exclusion file"):
        load_exclusions(discover=True, root=tmp_path)


def test_a_pattern_file_over_one_megabyte_is_refused(tmp_path):
    big = tmp_path / "big.ignore"
    big.write_text("#" * MAX_PATTERN_FILE_BYTES + "\n")
    with pytest.raises(ExclusionError, match="1 MB"):
        load_exclusions(files=[big])


def test_a_pattern_file_that_is_not_utf8_is_refused(tmp_path):
    bad = tmp_path / "bad.ignore"
    bad.write_bytes(b"\xff\xfe\x00*.env\n")
    with pytest.raises(ExclusionError, match="not UTF-8"):
        load_exclusions(files=[bad])


def test_more_than_the_pattern_limit_is_refused(tmp_path):
    many = tmp_path / "many.ignore"
    many.write_text("\n".join(f"file{i}.txt" for i in range(MAX_PATTERNS)) + "\n# fine\n\n")
    assert load_exclusions(files=[many]).excludes("file0.txt")
    with pytest.raises(ExclusionError, match="Too many exclusion patterns"):
        load_exclusions(["one-more.txt"], files=[many])
    with pytest.raises(ExclusionError):
        Exclusions(patterns=tuple(f"p{i}" for i in range(MAX_PATTERNS + 1)))


def test_exclusion_errors_are_value_errors():
    assert issubclass(ExclusionError, ValueError)


def test_as_exclusions_accepts_one_pattern_a_list_or_exclusions():
    assert not as_exclusions(None).active
    assert as_exclusions("*.env").excludes("a.env")
    assert as_exclusions(["*.env", "!keep.env"]).excluded(["a.env", "keep.env"]) == ["a.env"]
    ready = Exclusions(patterns=("x",))
    assert as_exclusions(ready) is ready


def test_excluded_lists_matches_once_in_order():
    exclusions = as_exclusions(["*.env"])
    assert exclusions.excluded(["b.env", "a.py", "b.env", "a.env"]) == ["b.env", "a.env"]


def test_the_note_names_the_path_and_the_reason():
    assert excluded_note("secrets/a.env") == (
        "secrets/a.env: excluded by the user's exclusion rules"
    )
