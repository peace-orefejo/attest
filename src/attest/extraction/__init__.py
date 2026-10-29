"""Bounded extraction of untrusted artifacts into detector-ready text segments."""

from __future__ import annotations

from .core import extract_artifact
from .limits import ExtractionLimits, ExtractionOutcome

__all__ = ["ExtractionLimits", "ExtractionOutcome", "extract_artifact"]
