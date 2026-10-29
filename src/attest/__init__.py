"""attest — evidence-grounded evaluation for AI agent trajectories."""

from .adapters.langgraph import from_langgraph_messages
from .api import Attest
from .checks.injection import (
    POSSIBLE_INJECTION_THRESHOLD,
    RegexDetector,
    RegexPattern,
    check_injection,
    load_regex_detector,
)
from .checks.judge_baseline import JudgeVerdict, naive_judge
from .checks.role import check_role_adherence
from .checks.tool_use import check_tool_use
from .checks.verify import extract_claims, grounded_verifier, judge_trajectory, verify_claims
from .content import Artifact, Detection, TextSegment
from .extraction import ExtractionLimits, ExtractionOutcome, extract_artifact
from .llm import Budget, BudgetExceeded, DiskCache, Usage
from .policy import EvaluationPolicy, EvaluationRule, check_policy, load_policy
from .providers import default_model, list_models
from .providers import providers as list_providers
from .results import PROMPT_VERSION, CheckResult, Finding, Report, Severity
from .scoring.report import evaluate
from .scoring.stats import Proportion, difference_is_real, wilson_interval
from .trajectory import Step, ToolCall, Trajectory

__all__ = [
    "POSSIBLE_INJECTION_THRESHOLD",
    "PROMPT_VERSION",
    "Artifact",
    "Attest",
    "Budget",
    "BudgetExceeded",
    "CheckResult",
    "Detection",
    "DiskCache",
    "EvaluationPolicy",
    "EvaluationRule",
    "ExtractionLimits",
    "ExtractionOutcome",
    "Finding",
    "JudgeVerdict",
    "Proportion",
    "RegexDetector",
    "RegexPattern",
    "Report",
    "Severity",
    "Step",
    "TextSegment",
    "ToolCall",
    "Trajectory",
    "Usage",
    "check_injection",
    "check_policy",
    "check_role_adherence",
    "check_tool_use",
    "default_model",
    "difference_is_real",
    "evaluate",
    "extract_artifact",
    "extract_claims",
    "from_langgraph_messages",
    "grounded_verifier",
    "judge_trajectory",
    "list_models",
    "list_providers",
    "load_policy",
    "load_regex_detector",
    "naive_judge",
    "verify_claims",
    "wilson_interval",
]

__version__ = "0.7.0"
