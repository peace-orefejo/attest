from pathlib import Path

from attest.code_review.evidence.lockfiles import VersionChange
from attest.code_review.evidence.lockfiles.pnpm import parse

FIXTURES = Path(__file__).parents[2] / "fixtures" / "lockfiles"


def test_v9_package_and_snapshot_keys():
    changes = parse((FIXTURES / "pnpm-lock.diff").read_text())
    assert changes == [
        VersionChange("axios", "1.6.2", "1.7.4"),
        VersionChange("@tanstack/query-core", "5.17.9", "5.28.4"),
        VersionChange("zod", None, "3.23.8"),
    ]


def test_v6_slash_keys_and_peer_suffixes():
    changes = parse((FIXTURES / "pnpm-lock-v6.diff").read_text())
    assert changes == [
        VersionChange("@babel/core", "7.23.6", "7.24.0"),
        VersionChange("react-dom", "18.2.0", "18.3.1"),
    ]


def test_v5_name_slash_version_keys():
    diff = (
        "--- a/pnpm-lock.yaml\n+++ b/pnpm-lock.yaml\n@@ -1,3 +1,3 @@\n"
        "-  /@types/react/18.2.0:\n"
        "+  /@types/react/18.2.48:\n"
        "-  /styled-components/6.1.0_react@18.2.0:\n"
        "+  /styled-components/6.1.8_react@18.2.0:\n"
    )
    assert parse(diff) == [
        VersionChange("@types/react", "18.2.0", "18.2.48"),
        VersionChange("styled-components", "6.1.0", "6.1.8"),
    ]


def test_importer_keys_are_not_packages():
    diff = (
        "--- a/pnpm-lock.yaml\n+++ b/pnpm-lock.yaml\n@@ -1,3 +1,4 @@\n"
        " importers:\n"
        "+  packages/api:\n"
        "   .:\n"
    )
    assert parse(diff) == []
