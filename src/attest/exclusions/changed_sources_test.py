"""Spotting a change set that edits one of the pattern files the exclusions came from."""

import os

import pytest

from attest.exclusions import changed_sources


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".attestignore").write_text("x\n")
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / "team.ignore").write_text("x\n")
    return tmp_path


def test_a_changed_source_is_found_wherever_the_repository_starts(repo, monkeypatch):
    sources = [str(repo / ".attestignore"), str(repo / "ci" / "team.ignore")]
    assert changed_sources(sources, ["ci/team.ignore"]) == [sources[1]]
    assert changed_sources(sources, ["./.attestignore"]) == [sources[0]]
    monkeypatch.chdir(repo.parent)
    relative = [f"{repo.name}/ci/team.ignore"]
    assert changed_sources(relative, ["ci/team.ignore"]) == relative


@pytest.mark.parametrize(
    "changed", ["b/.attestignore", ".ATTESTIGNORE", "ci/../.attestignore", "/.attestignore"]
)
def test_odd_forms_of_the_changed_path_still_match(repo, changed):
    source = str(repo / ".attestignore")
    assert changed_sources([source], [changed]) == [source]


def test_a_symlinked_source_matches_the_file_it_points_to(repo):
    link = repo / "linked.ignore"
    os.symlink(repo / "ci" / "team.ignore", link)
    assert changed_sources([str(link)], ["ci/team.ignore"]) == [str(link)]


def test_a_same_named_file_elsewhere_fails_safe(repo):
    source = str(repo / "ci" / "team.ignore")
    assert changed_sources([source], ["team.ignore"]) == [source]


def test_unrelated_changes_do_not_match(repo):
    sources = [str(repo / ".attestignore"), str(repo / "ci" / "team.ignore")]
    changed = ["docs/.attestignore", "other/team.ignore", "team.ignore.bak", "i/team.ignore"]
    assert changed_sources(sources, changed) == []
    assert changed_sources([], [".attestignore"]) == []
    assert changed_sources(sources, ["", "."]) == []
