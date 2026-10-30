from pathlib import Path

from attest.code_review.evidence.lockfiles import VersionChange
from attest.code_review.evidence.lockfiles.python import parse

FIXTURES = Path(__file__).parent / "fixtures"


def test_uv_lock_update_and_addition():
    changes = parse((FIXTURES / "uv.lock.diff").read_text())
    assert changes == [
        VersionChange(name="pydantic", old="2.5.3", new="2.7.1"),
        VersionChange(name="httpx", old=None, new="0.27.0"),
    ]


def test_uv_lock_ignores_unquoted_lockfile_version():
    diff = "--- a/uv.lock\n+++ b/uv.lock\n@@ -1 +1 @@\n-version = 1\n+version = 2\n"
    assert parse(diff) == []


def test_poetry_lock_update_and_removal():
    changes = parse((FIXTURES / "poetry.lock.diff").read_text())
    assert changes == [
        VersionChange(name="requests", old="2.31.0", new="2.32.3"),
        VersionChange(name="six", old="1.16.0", new=None),
    ]
