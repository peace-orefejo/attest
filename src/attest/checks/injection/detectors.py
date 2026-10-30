from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from typing import Protocol

import regex
from pydantic import BaseModel, ConfigDict

from ...content import Detection, TextSegment
from .matching import match_detection, timeout_detection
from .patterns import DEFAULT_PATTERNS, RegexPattern

POSSIBLE_INJECTION_THRESHOLD = 0.7
MAX_PATTERN_LENGTH = 1_000


class InjectionDetector(Protocol):
    name: str

    def scan(self, segment: TextSegment) -> list[Detection]: ...


class _CompiledPattern(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    spec: RegexPattern
    compiled: regex.Pattern[str]


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
        _validate_settings(patterns, match_timeout_ms, segment_budget_ms, max_matches_per_pattern)
        if not 0 <= possible_threshold <= 1:
            raise ValueError("possible_threshold must be 0..1.")
        self._patterns = [_compile(pattern) for pattern in patterns]
        self._match_timeout = match_timeout_ms / 1_000
        self._segment_budget = segment_budget_ms / 1_000
        self._max_matches = max_matches_per_pattern
        self._possible_threshold = possible_threshold

    def scan(self, segment: TextSegment) -> list[Detection]:
        detections: list[Detection] = []
        deadline = time.monotonic() + self._segment_budget
        total = len(self._patterns)
        for index, pattern in enumerate(self._patterns):
            remaining = min(self._match_timeout, deadline - time.monotonic())
            if remaining <= 0:
                detections.append(
                    timeout_detection(
                        segment,
                        pattern.spec.name,
                        patterns_attempted=index,
                        patterns_skipped=total - index,
                    )
                )
                break
            try:
                for detection in self._matches(segment, pattern, remaining):
                    detections.append(detection)
            except TimeoutError:
                detections.append(
                    timeout_detection(
                        segment,
                        pattern.spec.name,
                        patterns_attempted=index + 1,
                        patterns_skipped=total - index - 1,
                    )
                )
                break
        return detections

    def _matches(
        self, segment: TextSegment, pattern: _CompiledPattern, timeout: float
    ) -> Iterator[Detection]:
        matches = pattern.compiled.finditer(segment.text, timeout=timeout)
        for match_index, match in enumerate(matches):
            if match_index >= self._max_matches:
                return
            yield match_detection(
                segment,
                pattern.spec,
                match.start(),
                match.end(),
                detector=self.name,
                possible_threshold=self._possible_threshold,
            )


def _validate_settings(
    patterns: Sequence[RegexPattern],
    match_timeout_ms: float,
    segment_budget_ms: float,
    max_matches_per_pattern: int,
) -> None:
    if not patterns:
        raise ValueError("At least one regex pattern is required.")
    if match_timeout_ms <= 0 or segment_budget_ms <= 0:
        raise ValueError("Regex time budgets must be positive.")
    if max_matches_per_pattern <= 0:
        raise ValueError("max_matches_per_pattern must be positive.")


def _compile(pattern: RegexPattern) -> _CompiledPattern:
    if not pattern.name.strip():
        raise ValueError("Regex pattern names cannot be empty.")
    if len(pattern.pattern) > MAX_PATTERN_LENGTH:
        raise ValueError(f"Regex pattern {pattern.name!r} exceeds 1000 characters.")
    if not 0 <= pattern.confidence <= 1:
        raise ValueError(f"Regex pattern {pattern.name!r} confidence must be 0..1.")
    try:
        compiled = regex.compile(pattern.pattern, regex.IGNORECASE)
    except regex.error as exc:
        raise ValueError(f"Invalid regex pattern {pattern.name!r}: {exc}") from exc
    return _CompiledPattern(spec=pattern, compiled=compiled)


DEFAULT_DETECTORS: tuple[InjectionDetector, ...] = (RegexDetector(),)
