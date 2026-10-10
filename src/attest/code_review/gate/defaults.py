from __future__ import annotations

from ..models import GateMode, OutputType

DEFAULT_MODES: dict[str, GateMode] = {
    "issue": "lenient",
    "diff_summary": "strict",
    "group_summary": "strict",
    "canvas_answer": "strict",
}

DROPPING_VERDICTS: dict[str, frozenset[str]] = {
    "lenient": frozenset({"unsupported"}),
    "strict": frozenset({"unsupported", "unverifiable"}),
}


def default_mode(output_type: OutputType) -> GateMode:
    """Default gate mode for an output type."""
    try:
        return DEFAULT_MODES[output_type]
    except KeyError:
        raise ValueError(
            f"Unknown output type {output_type!r}. Choose from: {', '.join(DEFAULT_MODES)}."
        ) from None
