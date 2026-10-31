"""The published JSON Schemas match the CLI's output models."""

import json
from pathlib import Path

import pytest

from attest.cli.json_output import SCHEMA_VERSION, all_schemas

PUBLISHED = Path(__file__).resolve().parents[3] / "docs" / "schemas" / f"v{SCHEMA_VERSION}"


@pytest.mark.skipif(not PUBLISHED.is_dir(), reason="docs/ is not in this checkout")
@pytest.mark.parametrize("name", sorted(all_schemas()))
def test_published_schema_is_current(name):
    published = json.loads((PUBLISHED / f"{name}.json").read_text())
    assert published == all_schemas()[name], (
        "Regenerate with: uv run python docs/scripts/write_schemas.py"
    )
