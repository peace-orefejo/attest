"""The detector set ``check_injection`` runs when none is configured."""

from __future__ import annotations

from ..models import InjectionDetector
from .encoded import EncodedPayloadDetector
from .regex_detector import RegexDetector
from .unicode import UnicodeDetector

DEFAULT_DETECTORS: tuple[InjectionDetector, ...] = (
    RegexDetector(), UnicodeDetector(), EncodedPayloadDetector(),
)
