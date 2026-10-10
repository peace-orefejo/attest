import pytest

from attest.code_review.evidence.lockfiles.base import (
    LockfileParseError,
    VersionChange,
    collect_entries,
    format_summary,
    pair_changes,
)


def test_pairing_drops_versions_present_on_both_sides():
    changes = pair_changes(
        [("a", "1.0.0"), ("b", "2.0.0"), ("c", "1.0.0")],
        [("a", "1.1.0"), ("b", "2.0.0"), ("d", "0.1.0")],
    )
    assert changes == [
        VersionChange("a", "1.0.0", "1.1.0"),
        VersionChange("c", "1.0.0", None),
        VersionChange("d", None, "0.1.0"),
    ]


def test_kind():
    assert VersionChange("a", "1", "2").kind == "updated"
    assert VersionChange("a", None, "2").kind == "added"
    assert VersionChange("a", "1", None).kind == "removed"


def test_summary_caps_entries():
    changes = [VersionChange(f"pkg{i}", "1.0.0", "1.0.1") for i in range(50)]
    summary = format_summary("yarn.lock", 400, changes, max_entries=5)
    lines = summary.splitlines()
    assert len(lines) == 7
    assert lines[-1] == "  ... and 45 more changes"


def test_summary_without_version_changes():
    assert format_summary("go.sum", 2, []).endswith("no package version changes")


def test_text_without_hunks_is_unparseable():
    with pytest.raises(LockfileParseError):
        collect_entries("just some text")
