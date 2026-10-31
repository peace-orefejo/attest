from __future__ import annotations

import html
import json
import re

from ..utils.json_types import JsonObject

_BLOCK_TAG = re.compile(r"<(\s*/?\s*(?:tool_output|artifact))", re.IGNORECASE)


def evidence_block(index: int, name: str, arguments: JsonObject, output: str) -> str:
    rendered_arguments = json.dumps(arguments, default=str, ensure_ascii=False)
    return (
        f'<tool_output index="{index}" name="{html.escape(name)}" '
        f'arguments="{html.escape(rendered_arguments)}">\n'
        f"{escape_block_tags(output)}\n</tool_output>"
    )


def artifact_block(
    location: str,
    text: str,
    *,
    name: str | None,
    source: str,
    from_tool: str | None,
    complete: bool,
) -> str:
    attributes = [("location", location)]
    if name is not None:
        attributes.append(("name", name))
    attributes.append(("source", source))
    if from_tool is not None:
        attributes.append(("from_tool", from_tool))
    if not complete:
        attributes.append(("complete", "false"))
    rendered = " ".join(f'{key}="{html.escape(value)}"' for key, value in attributes)
    return f"<artifact {rendered}>\n{escape_block_tags(text)}\n</artifact>"


def escape_block_tags(text: str) -> str:
    """Escape anything that could open or close a <tool_output> or <artifact> block."""
    return _BLOCK_TAG.sub(r"&lt;\1", text)
