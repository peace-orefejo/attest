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


def test_a_changed_source_is_found_from_the_root_or_a_subdirectory(repo):
    sources = [str(repo / ".attestignore"), str(repo / "ci" / "team.ignore")]
    assert changed_sources(sources, ["ci/team.ignore"], root=repo) == [sources[1]]
    assert changed_sources(sources, ["./.attestignore"], root=repo / "ci") == [sources[0]]


@pytest.mark.parametrize("changed", ["b/.attestignore", ".ATTESTIGNORE", "ci/../.attestignore"])
def test_odd_forms_of_the_changed_path_still_match(repo, changed):
    source = str(repo / ".attestignore")
    assert changed_sources([source], [changed], root=repo) == [source]


def test_a_symlinked_source_matches_the_file_it_points_to(repo):
    link = repo / "linked.ignore"
    os.symlink(repo / "ci" / "team.ignore", link)
    assert changed_sources([str(link)], ["ci/team.ignore"], root=repo) == [str(link)]


def test_unrelated_changes_and_outside_sources_do_not_match(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "team.ignore"
    outside.write_text("x\n")
    sources = [str(repo / ".attestignore"), str(outside)]
    changed = ["docs/.attestignore", "team.ignore", "/abs/.attestignore"]
    assert changed_sources(sources, changed, root=repo) == []
    assert changed_sources([], [".attestignore"], root=repo) == []
