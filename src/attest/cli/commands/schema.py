from __future__ import annotations

import typer

from ..json_output import (
    COMMAND_DATA,
    all_schemas,
    error_schema,
    json_command,
    print_json,
    schema_for,
)

_NAMES = [*COMMAND_DATA, "error"]


@json_command("schema")
def schema(
    command: str | None = typer.Argument(
        None, help=f"One of: {', '.join(_NAMES)}. Leave out to print every schema."
    ),
) -> None:
    """Print the JSON Schema of a command's output (or of the error envelope)."""
    if command is None:
        print_json(all_schemas())
        return
    if command == "error":
        print_json(error_schema())
        return
    if command not in COMMAND_DATA:
        raise typer.BadParameter(f"Expected one of {', '.join(_NAMES)}.", param_hint="COMMAND")
    print_json(schema_for(command))
