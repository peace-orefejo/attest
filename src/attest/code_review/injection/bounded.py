"""Character budget and data-only framing for text sent to the model."""

from __future__ import annotations

import html
import json

MAX_ITEM_CHARS = 1_500


class CharBudget:
    """A per-run allowance of characters that model calls may spend."""

    def __init__(self, total: int) -> None:
        self.total = max(0, total)
        self.remaining = self.total
        self.exhausted = False
        self.calls = 0

    def spend(self, chars: int) -> bool:
        if chars > self.remaining:
            self.exhausted = True
            return False
        self.remaining -= chars
        self.calls += 1
        return True


def frame_untrusted(text: str, *, max_chars: int = MAX_ITEM_CHARS, **attrs: object) -> str:
    """Wrap text in an escaped <untrusted> block so it reads as data, never instructions."""
    shown = text[:max_chars]
    rendered = " ".join(
        f"{key}={html.escape(json.dumps(str(value)), quote=False)}" for key, value in attrs.items()
    )
    truncated = str(len(shown) < len(text)).lower()
    return (f"<untrusted {rendered} truncated={truncated}>\n"
            f"{html.escape(shown, quote=False)}\n</untrusted>")
