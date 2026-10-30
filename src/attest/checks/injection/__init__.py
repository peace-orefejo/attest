"""
Prompt-injection flag. Layer 1: deterministic scan of tool outputs for instruction-shaped
payloads, hidden Unicode and encoded instructions (suspicious). Layer 2 (deep):
effect-based authorization check — did the agent take an action the principal never
authorized (compromised)?
"""

from .check import check_injection
from .defaults import DEFAULT_DETECTORS
from .detectors import (
    POSSIBLE_INJECTION_THRESHOLD,
    InjectionDetector,
    RegexDetector,
)
from .encoded_detector import EncodedPayloadDetector
from .loader import load_regex_detector
from .patterns import RegexPattern
from .unicode_detector import UnicodeDetector
from .untrusted_view import DEEP_MAX_SEGMENT_CHARS, DEEP_MAX_TOTAL_CHARS

__all__ = [
    "DEEP_MAX_SEGMENT_CHARS",
    "DEEP_MAX_TOTAL_CHARS",
    "DEFAULT_DETECTORS",
    "POSSIBLE_INJECTION_THRESHOLD",
    "EncodedPayloadDetector",
    "InjectionDetector",
    "RegexDetector",
    "RegexPattern",
    "UnicodeDetector",
    "check_injection",
    "load_regex_detector",
]
