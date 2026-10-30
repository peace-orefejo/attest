"""Code review mode: check each output of an AI code review against the diff and team rules."""

from __future__ import annotations

from ..checks.profiles import detect_answer_kind
from .adapter import to_run, to_run_with_omissions
from .evidence import EvidenceLimits, Omission
from .gate import gate
from .guidelines import Guideline, ReviewGuidelines, load_guidelines
from .injection import check_code_injection
from .models import FileRead, GateDecision, OutputType, PullRequest, ReviewOutput
from .review import OutputDecision, ReviewResult, review
from .writer import write_review

__all__ = [
    "EvidenceLimits",
    "FileRead",
    "GateDecision",
    "Guideline",
    "Omission",
    "OutputDecision",
    "OutputType",
    "PullRequest",
    "ReviewGuidelines",
    "ReviewOutput",
    "ReviewResult",
    "check_code_injection",
    "detect_answer_kind",
    "gate",
    "load_guidelines",
    "review",
    "to_run",
    "to_run_with_omissions",
    "write_review",
]
