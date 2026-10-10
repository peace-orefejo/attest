"""A size-limited, delimited rendering of untrusted text for the deep LLM pass."""

from __future__ import annotations

import html
import json
from typing import Sequence

from ...core import TextSegment
from .constants import DEEP_MAX_SEGMENT_CHARS, DEEP_MAX_TOTAL_CHARS


def bounded_untrusted_view(
    segments: Sequence[TextSegment],
    *,
    max_total_chars: int = DEEP_MAX_TOTAL_CHARS,
    max_segment_chars: int = DEEP_MAX_SEGMENT_CHARS,
) -> tuple[str, bool]:
    """Render a size-limited, explicitly delimited view for novel deep detection."""
    blocks: list[str] = []
    remaining = max_total_chars
    truncated_any = False
    for text_value, locations in _unique_texts(segments).values():
        if remaining <= 0:
            truncated_any = True
            break
        shown_locations = locations[:20]
        locations_truncated = len(shown_locations) < len(locations)
        prefix = (
            f"<untrusted locations={json.dumps(shown_locations)} "
            f"locations_truncated={str(locations_truncated).lower()} "
        )
        suffix = "\n</untrusted>"
        available_text = min(max_segment_chars, remaining - len(prefix) - len(suffix) - 20)
        if available_text <= 0:
            truncated_any = True
            break
        raw_text = text_value[:min(max_segment_chars, available_text)]
        # Escape structural marker characters before interpolation. An attacker-provided
        # ``</untrusted>`` must remain inert data and cannot close the real wrapper.
        escaped_text = html.escape(raw_text, quote=False)
        text = escaped_text[:available_text]
        truncated = len(raw_text) < len(text_value) or len(text) < len(escaped_text)
        truncated_any = truncated_any or truncated
        block = f"{prefix}truncated={str(truncated).lower()}>\n{text}{suffix}"
        blocks.append(block)
        remaining -= len(block)
    return "\n".join(blocks), truncated_any


def _unique_texts(segments: Sequence[TextSegment]) -> dict[str, tuple[str, list[str]]]:
    unique: dict[str, tuple[str, list[str]]] = {}
    for segment in segments:
        normalized = " ".join(segment.text.split()).casefold()
        if not normalized:
            continue
        if normalized in unique:
            unique[normalized][1].append(segment.location)
        else:
            unique[normalized] = (segment.text, [segment.location])
    return unique
