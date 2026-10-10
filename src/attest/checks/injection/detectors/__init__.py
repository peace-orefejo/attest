"""Deterministic injection detectors, one module per detector."""

from .defaults import DEFAULT_DETECTORS
from .regex_detector import RegexDetector

__all__ = ["DEFAULT_DETECTORS", "RegexDetector"]
