from pathlib import Path

from attest.code_review.evidence.lockfiles import VersionChange
from attest.code_review.evidence.lockfiles.cargo import parse

FIXTURES = Path(__file__).parents[2] / "fixtures" / "lockfiles"


def test_update_and_addition():
    changes = parse((FIXTURES / "Cargo.lock.diff").read_text())
    assert changes == [
        VersionChange("serde", "1.0.190", "1.0.197"),
        VersionChange("syn", None, "2.0.52"),
    ]


def test_second_major_version_of_same_crate_is_an_addition():
    diff = (
        "--- a/Cargo.lock\n+++ b/Cargo.lock\n@@ -1,3 +1,7 @@\n"
        " [[package]]\n"
        ' name = "syn"\n'
        ' version = "1.0.109"\n'
        "+\n"
        "+[[package]]\n"
        '+name = "syn"\n'
        '+version = "2.0.52"\n'
    )
    assert parse(diff) == [VersionChange("syn", None, "2.0.52")]
