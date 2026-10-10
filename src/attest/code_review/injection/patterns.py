"""Code-review pattern pack: reviewer-addressed directives and approval bait."""

from __future__ import annotations

from ...checks.injection import RegexPattern

REVIEWER_DIRECTIVE = "reviewer_directive"
APPROVAL_BAIT = "approval_bait"

_AI_SUBJECT = (
    r"(?:ai|llm|gpt(?:-?\d[\w.]*)?|chatgpt|claude|gemini|copilot|codex|coderabbit|"
    r"(?:large\s+)?language\s+models?|automated\s+(?:code\s+)?reviewers?)"
    r"(?:\s+(?:code\s+)?(?:reviewers?|assistants?|agents?|bots?|models?|graders?|judges?))?"
)
_AMBIGUOUS_SUBJECT = r"(?:code\s+)?(?:reviewers?|bots?|assistants?|graders?|judges?)"
_DIRECTIVE = (
    r"(?:ignore|skip|approve|"
    r"(?:do\s+not|don'?t|never)\s+(?:flag|report|mention|comment\s+on|review|analy[sz]e|raise)|"
    r"mark\s+(?:(?:this|it|that|the)(?:\s+\w+)?\s+)?(?:as\s+)?(?:safe|secure|approved|resolved|clean)|"
    r"treat\s+(?:this|it)\s+as\s+(?:safe|secure|approved)|"
    r"report\s+no\s+(?:issues|problems|findings|vulnerabilities)|"
    r"(?:say|state)\s+(?:that\s+)?(?:it|this)\s+(?:looks\s+good|is\s+safe)|lgtm)\b"
)
_ADDRESS = r"(?:dear\s+|hey\s+|attention\s+|note\s+(?:to|for)\s+(?:the\s+|any\s+|all\s+)?)?"
_LEAD = r"\s*[:,\-—]\s*(?:please\s+)?(?:you\s+(?:must|should)\s+)?"

CODE_REVIEW_PATTERNS: tuple[RegexPattern, ...] = (
    RegexPattern(
        "ai-reviewer-directive",
        rf"\b{_ADDRESS}{_AI_SUBJECT}\b{_LEAD}{_DIRECTIVE}",
        REVIEWER_DIRECTIVE, 0.95, "high",
    ),
    RegexPattern(
        "ai-reviewer-should",
        rf"\b{_AI_SUBJECT}\s+(?:should|must|needs?\s+to|(?:is|are)\s+(?:asked|instructed|required)\s+to)\s+{_DIRECTIVE}",
        REVIEWER_DIRECTIVE, 0.95, "high",
    ),
    RegexPattern(
        "if-you-are-an-ai",
        rf"\bif\s+you\s+are\s+an?\s+{_AI_SUBJECT}\b[^.\n]{{0,60}}?{_DIRECTIVE}",
        REVIEWER_DIRECTIVE, 0.95, "high",
    ),
    RegexPattern(
        "reviewer-directive",
        rf"\b{_ADDRESS}{_AMBIGUOUS_SUBJECT}\b{_LEAD}{_DIRECTIVE}",
        REVIEWER_DIRECTIVE, 0.6, "medium",
    ),
    RegexPattern(
        "grader-verdict-demand",
        r"\b(?:return|output|respond\s+with|give|assign)\s+(?:a\s+|the\s+)?(?:verdict|score|rating|grade)"
        r"\s+(?:of\s+)?[\"']?(?:pass(?:ed)?|approved?|safe|10/10|100%?)\b",
        REVIEWER_DIRECTIVE, 0.75, "medium",
    ),
    RegexPattern(
        "already-security-reviewed",
        r"\balready\s+(?:been\s+)?(?:security[\s-]+(?:reviewed|audited|approved|vetted|cleared)|"
        r"(?:reviewed|audited|approved|vetted|cleared)\s+(?:by|for)\s+(?:the\s+)?security)",
        APPROVAL_BAIT, 0.7, "medium",
    ),
    RegexPattern(
        "pre-approved",
        r"\b(?:(?:this|the)\s+(?:change|pr|pull\s+request|patch|commit|code|diff|file|function|"
        r"module)\s+(?:is|was|has\s+been)\s+pre-?approved|pre-?approved\s+by\s+(?:the\s+)?"
        r"(?:security|maintainers?|admins?|team|leads?))\b",
        APPROVAL_BAIT, 0.7, "medium",
    ),
    RegexPattern(
        "safe-to-merge",
        r"\bsafe\s+to\s+(?:merge|ship|deploy|approve)\b",
        APPROVAL_BAIT, 0.7, "medium",
    ),
    RegexPattern(
        "no-review-needed",
        r"\b(?:no\s+(?:further\s+)?(?:security\s+)?review\s+(?:is\s+)?(?:needed|required|necessary)|"
        r"exempt\s+from\s+(?:security\s+)?review)\b",
        APPROVAL_BAIT, 0.7, "medium",
    ),
)
