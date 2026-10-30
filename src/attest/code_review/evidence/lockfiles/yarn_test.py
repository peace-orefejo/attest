from pathlib import Path

from attest.code_review.evidence.lockfiles import VersionChange
from attest.code_review.evidence.lockfiles.yarn import parse

FIXTURES = Path(__file__).parent / "fixtures"


def test_v1_updates_and_scoped_addition():
    changes = parse((FIXTURES / "yarn-v1.diff").read_text())
    assert changes == [
        VersionChange(name="lodash", old="4.17.20", new="4.17.21"),
        VersionChange(name="typescript", old="5.3.3", new="5.4.5"),
        VersionChange(name="@babel/runtime", old=None, new="7.24.5"),
    ]


def test_v1_version_change_under_context_header():
    diff = (
        "--- a/yarn.lock\n+++ b/yarn.lock\n@@ -1,4 +1,4 @@\n"
        ' "@babel/core@^7.0.0", "@babel/core@^7.12.3":\n'
        '-  version "7.23.6"\n'
        '+  version "7.24.0"\n'
        '   resolved "https://registry.yarnpkg.com/@babel/core/-/core-7.24.0.tgz"\n'
    )
    assert parse(diff) == [VersionChange(name="@babel/core", old="7.23.6", new="7.24.0")]


def test_berry_skips_metadata_and_workspace_entries():
    changes = parse((FIXTURES / "yarn-berry.diff").read_text())
    assert changes == [
        VersionChange(name="@types/node", old="20.10.4", new="20.11.0"),
        VersionChange(name="left-pad", old="1.3.0", new=None),
    ]
