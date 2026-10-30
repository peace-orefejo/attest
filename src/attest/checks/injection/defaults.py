from __future__ import annotations

from .detectors import InjectionDetector, RegexDetector
from .encoded_detector import EncodedPayloadDetector
from .unicode_detector import UnicodeDetector

DEFAULT_DETECTORS: tuple[InjectionDetector, ...] = (
    RegexDetector(),
    UnicodeDetector(),
    EncodedPayloadDetector(),
)
