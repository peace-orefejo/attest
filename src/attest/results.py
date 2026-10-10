"""Compatibility path for attest.core.results."""

from .core.results import PROMPT_VERSION, CheckResult, Finding, Report, Severity

__all__ = ["PROMPT_VERSION", "CheckResult", "Finding", "Report", "Severity"]
