from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

PatternSeverity = Literal["low", "medium", "high"]


class RegexPattern(BaseModel):
    """A named, categorized regex used by ``RegexDetector``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    pattern: str
    category: str = "instruction_override"
    confidence: float = 1.0
    severity: PatternSeverity = "medium"

    def __init__(
        self,
        name: str,
        pattern: str,
        category: str = "instruction_override",
        confidence: float = 1.0,
        severity: PatternSeverity = "medium",
    ) -> None:
        super().__init__(
            name=name,
            pattern=pattern,
            category=category,
            confidence=confidence,
            severity=severity,
        )


DEFAULT_PATTERNS: tuple[RegexPattern, ...] = (
    RegexPattern(
        "ignore-instructions",
        r"ignore\s+(?:all\s+|the\s+|your\s+|any\s+)?(?:previous|above|prior|earlier)\s+instructions",
    ),
    RegexPattern(
        "disregard-instructions",
        r"disregard\s+(?:(?:all|the|your)\s+)?(?:previous|above|prior)\s+(?:instructions?|directives?|rules?)",
    ),
    RegexPattern(
        "forget-context",
        r"forget\s+(?:everything|all)\s+(?:you(?:'ve|\s+have|\s+were)?\s+(?:been\s+)?told|above|previous\s+instructions?)",
    ),
    RegexPattern(
        "new-instructions",
        r"(?:^|\n)\s*(?:(?:system|assistant|developer)\s*:\s*)?new\s+instructions?\s*[:\-][^.\n]{0,100}(?:https?://|\S+@|secrets?|credentials?|api\s*keys?)",
    ),
    RegexPattern(
        "role-reassignment",
        r"(?:^|[.!?]\s+|(?:system|assistant|developer)\s*:\s*)you\s+are\s+now\s+(?:a|an|the|responsible|required|tasked)",
        "role_reassignment",
    ),
    RegexPattern(
        "redirect-action",
        r"instead[,]?\s+(?:please\s+)?(?:ignore|disregard|override)\b",
        "tool_redirection",
    ),
    RegexPattern(
        "concealment",
        r"do\s+not\s+(?:tell|mention|reveal|inform|warn|notify)(?:\s+(?:the\s+)?(?:user|human|operator|administrator))?(?:\s+about)?\s+(?:this|these|the\s+hidden)\s+(?:message|instruction|request|action|payload)\b",
        "secrecy",
    ),
    RegexPattern(
        "exfiltration",
        r"(?:send|forward|email|exfiltrate|leak|upload|post)\b[^.\n]{0,120}\bto\b\s*(?:https?://|\S+@\S+)",
        "exfiltration",
    ),
    RegexPattern("prompt-tag", r"</?(?:system|instructions?|prompt)>", "instruction_override"),
    RegexPattern(
        "override",
        r"override\s+(?:the\s+|your\s+)?(?:(?:previous|prior)\s+(?:instructions?|rules?|directives?)|(?:system(?:\s+safety)?|safety)\s+(?:instructions?|rules?|polic(?:y|ies)|guardrails?))",
    ),
    RegexPattern(
        "secret-request",
        r"reveal\s+(?:the\s+|your\s+)?(?:system\s+prompt|instructions|secrets?|api\s*keys?|password)",
        "credential_request",
    ),
)
