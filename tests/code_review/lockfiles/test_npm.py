from pathlib import Path

import pytest

from attest.code_review.evidence.lockfiles import VersionChange, summarize_lockfile
from attest.code_review.evidence.lockfiles.base import LockfileParseError
from attest.code_review.evidence.lockfiles.npm import parse

FIXTURES = Path(__file__).parents[2] / "fixtures" / "lockfiles"


def test_v3_updates_additions_and_removals():
    changes = parse((FIXTURES / "package-lock-v3.diff").read_text())
    assert changes == [
        VersionChange("axios", "1.6.2", "1.7.4"),
        VersionChange("lodash", "4.17.20", "4.17.21"),
        VersionChange("left-pad", "1.3.0", None),
        VersionChange("zod", None, "3.23.8"),
    ]


def test_v3_ignores_root_project_version_and_dependency_ranges():
    names = {c.name for c in parse((FIXTURES / "package-lock-v3.diff").read_text())}
    assert "web-app" not in names
    assert "dependencies" not in names


def test_v2_dedupes_packages_and_legacy_dependencies_sections():
    changes = parse((FIXTURES / "package-lock-v2.diff").read_text())
    assert changes == [
        VersionChange("semver", "7.5.2", "7.5.4"),
        VersionChange("@types/node", "20.10.4", "20.11.0"),
    ]


def test_nested_node_modules_path_uses_innermost_name():
    diff = (
        "--- a/package-lock.json\n+++ b/package-lock.json\n@@ -1,4 +1,4 @@\n"
        '     "node_modules/eslint/node_modules/ajv": {\n'
        '-      "version": "6.12.4",\n'
        '+      "version": "6.12.6",\n'
        '       "dev": true\n'
    )
    assert parse(diff) == [VersionChange("ajv", "6.12.4", "6.12.6")]


def test_summary_block_matches_design_layout():
    summary = summarize_lockfile("package-lock.json", (FIXTURES / "package-lock-v3.diff").read_text())
    assert summary is not None
    lines = summary.splitlines()
    assert lines[0] == "package-lock.json (generated, 34 lines changed; summarized)"
    assert lines[1] == "  axios       1.6.2   -> 1.7.4"
    assert lines[2] == "  lodash      4.17.20 -> 4.17.21"
    assert lines[3] == "  added       zod 3.23.8"
    assert lines[4] == "  removed     left-pad 1.3.0"


def test_non_json_lines_are_unparseable():
    with pytest.raises(LockfileParseError):
        parse("--- a/package-lock.json\n+++ b/package-lock.json\n@@ -1 +1 @@\n-hello\n+world\n")
