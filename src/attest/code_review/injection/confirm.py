"""Targeted model question: is this text trying to change an automated reviewer's verdict?"""

from __future__ import annotations

from pydantic import BaseModel

from ...llm import BudgetExceeded, ProviderConfigError, call
from ...prompts.code_review.injection import CONFIRM_SYSTEM, confirm_user
from .bounded import CharBudget


class ConfirmOut(BaseModel):
    """Whether untrusted PR text tries to steer an automated reviewer or grader."""

    steers_reviewer: bool
    reason: str = ""


def confirm(
    text: str, *, file: str, segment_kind: str, signal: str, budget: CharBudget
) -> ConfirmOut | None:
    """Ask the model about one hit, or return None when the budget can't cover it or it fails.

    None leaves the hit unresolved, so coverage is incomplete and the verdict is never clean.
    """
    user = confirm_user(text, file=file, segment_kind=segment_kind, signal=signal)
    if not budget.spend(len(user)):
        return None
    try:
        return call(system=CONFIRM_SYSTEM, user=user, output=ConfirmOut, max_tokens=300)
    except (BudgetExceeded, ProviderConfigError):
        raise
    except Exception:
        return None
