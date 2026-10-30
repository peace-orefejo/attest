"""The judge's reported rule violations, and which of them to accept."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from .models import Guideline, ReviewGuidelines

MIN_QUOTE_WORDS = 3

ViolationKind = Literal["breaks", "misses"]


class Violation(BaseModel):
    rule: str
    kind: ViolationKind = "breaks"
    quote: str
    reason: str = ""


class ViolationsOut(BaseModel):
    violations: list[Violation] = Field(default_factory=list[Violation])


class Accepted(BaseModel):
    violation: Violation
    rule: Guideline


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def accept(violations: list[Violation], guidelines: ReviewGuidelines, text: str) -> list[Accepted]:
    """Keep violations naming a real rule and quoting the output; a break hides its rule's miss."""
    valid: dict[tuple[str, ViolationKind], Accepted] = {}
    for violation in violations:
        rule = guidelines.get(violation.rule.strip().upper())
        if rule is None or not _quotes_output(normalize(violation.quote), text):
            continue
        valid.setdefault((rule.id, violation.kind), Accepted(violation=violation, rule=rule))
    broken = {rule_id for rule_id, kind in valid if kind == "breaks"}
    return [
        accepted
        for (rule_id, kind), accepted in valid.items()
        if kind == "breaks" or rule_id not in broken
    ]


def _quotes_output(quote: str, text: str) -> bool:
    if not quote or quote not in text:
        return False
    return len(quote.split()) >= MIN_QUOTE_WORDS or quote == text
