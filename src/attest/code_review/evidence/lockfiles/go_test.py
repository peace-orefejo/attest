from pathlib import Path

import pytest

from attest.code_review.evidence.lockfiles import VersionChange
from attest.code_review.evidence.lockfiles.base import LockfileParseError
from attest.code_review.evidence.lockfiles.go import parse

FIXTURES = Path(__file__).parent / "fixtures"


def test_update_and_addition_dedupe_go_mod_lines():
    changes = parse((FIXTURES / "go.sum.diff").read_text())
    assert changes == [
        VersionChange(name="github.com/google/uuid", old="v1.4.0", new="v1.6.0"),
        VersionChange(name="golang.org/x/sync", old=None, new="v0.7.0"),
    ]


def test_unrecognized_lines_are_unparseable():
    with pytest.raises(LockfileParseError):
        parse("--- a/go.sum\n+++ b/go.sum\n@@ -1 +1 @@\n-not a sum line\n+still not\n")
