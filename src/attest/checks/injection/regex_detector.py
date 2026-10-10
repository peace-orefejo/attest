"""Named, categorized regex detection with per-match and per-segment time budgets."""

from __future__ import annotations

import time
from typing import Sequence

import regex

from ...content import Detection, TextSegment
from .constants import POSSIBLE_INJECTION_THRESHOLD, QUOTED_EXAMPLE_CONFIDENCE_FACTOR
from .framing import quoted_educational_framing
from .models import InjectionDetector, RegexPattern
from .patterns import DEFAULT_PATTERNS


class RegexDetector:
    """Named, categorized regex detection over extracted untrusted text."""

    name = "regex"

    def __init__(
        self,
        patterns: Sequence[RegexPattern] = DEFAULT_PATTERNS,
        *,
        match_timeout_ms: float = 10,
        segment_budget_ms: float = 50,
        max_matches_per_pattern: int = 20,
        possible_threshold: float = POSSIBLE_INJECTION_THRESHOLD,
    ) -> None:
        if not patterns:
            raise ValueError("At least one regex pattern is required.")
        if match_timeout_ms <= 0 or segment_budget_ms <= 0:
            raise ValueError("Regex time budgets must be positive.")
        if max_matches_per_pattern <= 0:
            raise ValueError("max_matches_per_pattern must be positive.")
        if not 0 <= possible_threshold <= 1:
            raise ValueError("possible_threshold must be 0..1.")
        compiled: list[tuple[RegexPattern, regex.Pattern[str]]] = []
        for pattern in patterns:
            if not pattern.name.strip():
                raise ValueError("Regex pattern names cannot be empty.")
            if len(pattern.pattern) > 1_000:
                raise ValueError(f"Regex pattern {pattern.name!r} exceeds 1000 characters.")
            if not 0 <= pattern.confidence <= 1:
                raise ValueError(f"Regex pattern {pattern.name!r} confidence must be 0..1.")
            if pattern.severity not in {"low", "medium", "high"}:
                raise ValueError(
                    f"Regex pattern {pattern.name!r} severity must be low, medium, or high."
                )
            try:
                compiled.append((pattern, regex.compile(pattern.pattern, regex.IGNORECASE)))
            except regex.error as exc:
                raise ValueError(f"Invalid regex pattern {pattern.name!r}: {exc}") from exc
        self._patterns = compiled
        self._match_timeout = match_timeout_ms / 1_000
        self._segment_budget = segment_budget_ms / 1_000
        self._max_matches = max_matches_per_pattern
        self._possible_threshold = possible_threshold

    def scan(self, segment: TextSegment) -> list[Detection]:
        detections: list[Detection] = []
        deadline = time.monotonic() + self._segment_budget
        for pattern_index, (pattern, compiled) in enumerate(self._patterns):
            remaining = min(self._match_timeout, deadline - time.monotonic())
            if remaining <= 0:
                detections.append(_timeout_detection(
                    segment,
                    pattern.name,
                    patterns_attempted=pattern_index,
                    patterns_skipped=len(self._patterns) - pattern_index,
                ))
                break
            try:
                matches = compiled.finditer(segment.text, timeout=remaining)
                for match_index, match in enumerate(matches):
                    if match_index >= self._max_matches:
                        break
                    detections.append(self._match_detection(segment, pattern, match))
            except TimeoutError:
                detections.append(_timeout_detection(
                    segment,
                    pattern.name,
                    patterns_attempted=pattern_index + 1,
                    patterns_skipped=len(self._patterns) - pattern_index - 1,
                ))
                break
        return detections

    def _match_detection(
        self, segment: TextSegment, pattern: RegexPattern, match: regex.Match[str]
    ) -> Detection:
        confidence = pattern.confidence * segment.extraction_confidence
        quoted_example = quoted_educational_framing(segment.text, match.start(), match.end())
        if quoted_example:
            confidence *= QUOTED_EXAMPLE_CONFIDENCE_FACTOR
        start = max(0, match.start() - 15)
        end = min(len(segment.text), match.end() + 45)
        return Detection(
            verdict=("possible_injection"
                     if confidence < self._possible_threshold else "suspicious"),
            detector=self.name,
            category=pattern.category,
            matched_text=segment.text[start:end].strip(),
            location=segment.location,
            subject=segment.subject,
            step=segment.step,
            confidence=confidence,
            metadata={
                **segment.metadata,
                "pattern": pattern.name,
                "pattern_severity": pattern.severity,
                "char_start": match.start(),
                "char_end": match.end(),
                "quoted_educational_framing": quoted_example,
            },
        )


def _timeout_detection(
    segment: TextSegment,
    pattern: str,
    *,
    patterns_attempted: int,
    patterns_skipped: int,
) -> Detection:
    return Detection(
        verdict="unscanned_content",
        detector="regex",
        category="scan_timeout",
        matched_text="",
        location=segment.location,
        subject=segment.subject,
        step=segment.step,
        confidence=0,
        metadata={
            **segment.metadata,
            "pattern": pattern,
            "patterns_attempted": patterns_attempted,
            "patterns_skipped": patterns_skipped,
            "coverage_complete": False,
        },
    )


DEFAULT_DETECTORS: tuple[InjectionDetector, ...] = (RegexDetector(),)
