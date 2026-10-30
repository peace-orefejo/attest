from pathlib import Path

from attest.code_review.evidence.lockfiles import VersionChange
from attest.code_review.evidence.lockfiles.pnpm import parse

FIXTURES = Path(__file__).parent / "fixtures"


def test_v9_package_and_snapshot_keys():
    changes = parse((FIXTURES / "pnpm-lock.diff").read_text())
    assert changes == [
        VersionChange(name="axios", old="1.6.2", new="1.7.4"),
        VersionChange(name="@tanstack/query-core", old="5.17.9", new="5.28.4"),
        VersionChange(name="zod", old=None, new="3.23.8"),
    ]


def test_v6_slash_keys_and_peer_suffixes():
    changes = parse((FIXTURES / "pnpm-lock-v6.diff").read_text())
    assert changes == [
        VersionChange(name="@babel/core", old="7.23.6", new="7.24.0"),
        VersionChange(name="react-dom", old="18.2.0", new="18.3.1"),
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
        VersionChange(name="@types/react", old="18.2.0", new="18.2.48"),
        VersionChange(name="styled-components", old="6.1.0", new="6.1.8"),
    ]


def test_importer_keys_are_not_packages():
    diff = (
        "--- a/pnpm-lock.yaml\n+++ b/pnpm-lock.yaml\n@@ -1,3 +1,4 @@\n"
        " importers:\n"
        "+  packages/api:\n"
        "   .:\n"
    )
    assert parse(diff) == []
