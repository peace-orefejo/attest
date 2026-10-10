from pathlib import Path

from attest.code_review.evidence.lockfiles import VersionChange
from attest.code_review.evidence.lockfiles.yarn import parse

FIXTURES = Path(__file__).parents[2] / "fixtures" / "lockfiles"


def test_v1_updates_and_scoped_addition():
    changes = parse((FIXTURES / "yarn-v1.diff").read_text())
    assert changes == [
        VersionChange("lodash", "4.17.20", "4.17.21"),
        VersionChange("typescript", "5.3.3", "5.4.5"),
        VersionChange("@babel/runtime", None, "7.24.5"),
    ]


def test_v1_version_change_under_context_header():
    diff = (
        "--- a/yarn.lock\n+++ b/yarn.lock\n@@ -1,4 +1,4 @@\n"
        ' "@babel/core@^7.0.0", "@babel/core@^7.12.3":\n'
        '-  version "7.23.6"\n'
        '+  version "7.24.0"\n'
        '   resolved "https://registry.yarnpkg.com/@babel/core/-/core-7.24.0.tgz"\n'
    )
    assert parse(diff) == [VersionChange("@babel/core", "7.23.6", "7.24.0")]


def test_berry_skips_metadata_and_workspace_entries():
    changes = parse((FIXTURES / "yarn-berry.diff").read_text())
    assert changes == [
        VersionChange("@types/node", "20.10.4", "20.11.0"),
        VersionChange("left-pad", "1.3.0", None),
    ]
