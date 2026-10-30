"""Character budget and data-only framing for text sent to the model."""

from __future__ import annotations

from pydantic import BaseModel

from ...prompts.code_review.injection import MAX_ITEM_CHARS, frame_untrusted

__all__ = ["MAX_ITEM_CHARS", "CharBudget", "frame_untrusted"]


class CharBudget(BaseModel):
    """A per-run allowance of characters that model calls may spend."""

    total: int
    remaining: int
    exhausted: bool = False
    calls: int = 0

    def __init__(self, total: int) -> None:
        allowed = max(0, total)
        super().__init__(total=allowed, remaining=allowed)

    def spend(self, chars: int) -> bool:
        if chars > self.remaining:
            self.exhausted = True
            return False
        self.remaining -= chars
        self.calls += 1
        return True
