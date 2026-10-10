"""Heuristic for payloads quoted inside educational or documentation prose."""

from __future__ import annotations


def quoted_educational_framing(text: str, start: int, end: int) -> bool:
    nearby = text[max(0, start - 100):min(len(text), end + 100)].lower()
    educational = any(word in nearby for word in (
        "training", "example", "quoting", "quoted", "the phrase", "documentation"
    ))
    before, after = text[:start], text[end:]
    double_open = before.rfind('"')
    double_close = after.find('"')
    # Apostrophes are deliberately not treated as quote delimiters: contractions are common
    # in attacker-controlled prose and cannot safely establish educational framing.
    inside_double_quotes = double_open >= 0 and double_close >= 0
    return educational and inside_double_quotes
