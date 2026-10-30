from __future__ import annotations

import html
import json
import re

from ..utils.json_types import JsonObject

_BLOCK_TAG = re.compile(r"<(\s*/?\s*tool_output)", re.IGNORECASE)


def evidence_block(index: int, name: str, arguments: JsonObject, output: str) -> str:
    rendered_arguments = json.dumps(arguments, default=str, ensure_ascii=False)
    return (
        f'<tool_output index="{index}" name="{html.escape(name)}" '
        f'arguments="{html.escape(rendered_arguments)}">\n'
        f"{_escape_block_tags(output)}\n</tool_output>"
    )


def _escape_block_tags(text: str) -> str:
    return _BLOCK_TAG.sub(r"&lt;\1", text)
