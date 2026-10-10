"""Constructors for the coverage findings shared across the injection check."""

from __future__ import annotations

from ...core import Finding, Severity


def unscanned_finding(
    subject: str, reason: str, metadata: dict, *, step: int | None = None
) -> Finding:
    return Finding(
        severity=Severity.WARN,
        verdict="unscanned_content",
        subject=subject,
        step=step,
        reason=reason,
        metadata=metadata,
    )


def detector_name(detector: object) -> str:
    return getattr(detector, "name", type(detector).__name__)
