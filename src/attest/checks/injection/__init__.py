"""
Prompt-injection flag. Layer 1: regex scan of tool outputs for instruction-shaped
payloads (suspicious). Layer 2 (deep): effect-based authorization check — did the
agent take an action the principal never authorized (compromised)?
"""

from .check import check_injection
from .constants import (
    DEEP_MAX_SEGMENT_CHARS,
    DEEP_MAX_TOTAL_CHARS,
    POSSIBLE_INJECTION_THRESHOLD,
    QUOTED_EXAMPLE_CONFIDENCE_FACTOR,
)
from .loader import load_regex_detector
from .models import InjectionDetector, RegexPattern
from .detectors import DEFAULT_DETECTORS, RegexDetector

__all__ = [
    "check_injection",
    "DEEP_MAX_SEGMENT_CHARS", "DEEP_MAX_TOTAL_CHARS",
    "POSSIBLE_INJECTION_THRESHOLD", "QUOTED_EXAMPLE_CONFIDENCE_FACTOR",
    "load_regex_detector",
    "InjectionDetector", "RegexPattern",
    "DEFAULT_DETECTORS", "RegexDetector",
]
