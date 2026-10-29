from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

from ...content import TextSegment
from ...utils.markup import escape_markup

DEEP_MAX_TOTAL_CHARS = 8_000
DEEP_MAX_SEGMENT_CHARS = 2_000
MAX_SHOWN_LOCATIONS = 20
_BLOCK_SUFFIX = "\n</untrusted>"
_BLOCK_SLACK = 20


class UntrustedView(BaseModel):
    text: str
    truncated: bool


class _UniqueText(BaseModel):
    text: str
    locations: list[str]


class _RenderedBlock(BaseModel):
    text: str
    truncated: bool


def bounded_untrusted_view(
    segments: Sequence[TextSegment],
    *,
    max_total_chars: int = DEEP_MAX_TOTAL_CHARS,
    max_segment_chars: int = DEEP_MAX_SEGMENT_CHARS,
) -> UntrustedView:
    """Render a size-limited, explicitly delimited view for novel deep detection."""
    blocks: list[str] = []
    remaining = max_total_chars
    truncated = False
    for unique in _deduplicate(segments):
        block = _render_block(unique, remaining, max_segment_chars)
        if block is None:
            truncated = True
            break
        blocks.append(block.text)
        truncated = truncated or block.truncated
        remaining -= len(block.text)
    return UntrustedView(text="\n".join(blocks), truncated=truncated)


def _deduplicate(segments: Sequence[TextSegment]) -> list[_UniqueText]:
    unique: dict[str, _UniqueText] = {}
    for segment in segments:
        normalized = " ".join(segment.text.split()).casefold()
        if not normalized:
            continue
        if normalized in unique:
            unique[normalized].locations.append(segment.location)
        else:
            unique[normalized] = _UniqueText(text=segment.text, locations=[segment.location])
    return list(unique.values())


def _render_block(
    unique: _UniqueText, remaining: int, max_segment_chars: int
) -> _RenderedBlock | None:
    if remaining <= 0:
        return None
    shown_locations = unique.locations[:MAX_SHOWN_LOCATIONS]
    locations_truncated = len(shown_locations) < len(unique.locations)
    prefix = (
        f"<untrusted locations={json.dumps(shown_locations)} "
        f"locations_truncated={str(locations_truncated).lower()} "
    )
    available_text = min(
        max_segment_chars, remaining - len(prefix) - len(_BLOCK_SUFFIX) - _BLOCK_SLACK
    )
    if available_text <= 0:
        return None
    raw_text = unique.text[:available_text]
    # Escape structural marker characters before interpolation. An attacker-provided
    # ``</untrusted>`` must remain inert data and cannot close the real wrapper.
    escaped_text = escape_markup(raw_text)
    text = escaped_text[:available_text]
    truncated = len(raw_text) < len(unique.text) or len(text) < len(escaped_text)
    return _RenderedBlock(
        text=f"{prefix}truncated={str(truncated).lower()}>\n{text}{_BLOCK_SUFFIX}",
        truncated=truncated,
    )
