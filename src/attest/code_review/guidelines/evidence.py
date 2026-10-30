"""Fit tagged evidence into a character limit without leaving a block open."""

from __future__ import annotations

_CLOSE = "</tool_output>"


def fit_evidence(evidence: str, max_chars: int) -> str:
    """Cut evidence at the last whole <tool_output> block that fits, closing a cut first block."""
    if len(evidence) <= max_chars:
        return evidence
    end = evidence.rfind(_CLOSE, 0, max_chars)
    if end >= 0:
        return evidence[: end + len(_CLOSE)]
    return f"{evidence[: max(0, max_chars - len(_CLOSE) - 1)]}\n{_CLOSE}"
