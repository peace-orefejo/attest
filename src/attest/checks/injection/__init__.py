"""
Prompt-injection flag. Layer 1: regex scan of tool outputs for instruction-shaped
payloads (suspicious). Layer 2 (deep): effect-based authorization check — did the
agent take an action the principal never authorized (compromised)?
"""

from .check import check_injection
from .detectors import (
    DEFAULT_DETECTORS,
    POSSIBLE_INJECTION_THRESHOLD,
    InjectionDetector,
    RegexDetector,
)
from .loader import load_regex_detector
from .patterns import RegexPattern
from .untrusted_view import DEEP_MAX_SEGMENT_CHARS, DEEP_MAX_TOTAL_CHARS

__all__ = [
    "DEEP_MAX_SEGMENT_CHARS",
    "DEEP_MAX_TOTAL_CHARS",
    "DEFAULT_DETECTORS",
    "POSSIBLE_INJECTION_THRESHOLD",
    "InjectionDetector",
    "RegexDetector",
    "RegexPattern",
    "check_injection",
    "load_regex_detector",
]
