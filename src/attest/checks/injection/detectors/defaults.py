"""The detector set ``check_injection`` runs when none is configured."""

from __future__ import annotations

from ..models import InjectionDetector
from .regex_detector import RegexDetector

DEFAULT_DETECTORS: tuple[InjectionDetector, ...] = (RegexDetector(),)
