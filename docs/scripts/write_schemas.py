"""Write the JSON Schema of every CLI command's output to docs/schemas/v1/.

uv run python docs/scripts/write_schemas.py
"""

from __future__ import annotations

import json
from pathlib import Path

from attest.cli.json_output import SCHEMA_VERSION, all_schemas

OUT = Path(__file__).resolve().parent.parent / "schemas" / f"v{SCHEMA_VERSION}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, schema in all_schemas().items():
        (OUT / f"{name}.json").write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    main()
