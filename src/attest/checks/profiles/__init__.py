"""Answer-kind profiles: which prompts grade an answer, and auto-detection of the kind."""

from __future__ import annotations

from .detect import KindDetection, detect_answer_kind
from .registry import AUTO, PROFILE_KINDS, SUPPORTED_ANSWER_KINDS, Profile, get_profile
from .resolve import ResolvedKind, resolve_answer_kind

__all__ = [
    "AUTO",
    "PROFILE_KINDS",
    "SUPPORTED_ANSWER_KINDS",
    "KindDetection",
    "Profile",
    "ResolvedKind",
    "detect_answer_kind",
    "get_profile",
    "resolve_answer_kind",
]
