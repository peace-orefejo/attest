"""attest — evidence-grounded evaluation for AI agent trajectories."""

from .core.trajectory import Trajectory, Step, ToolCall
from .core.content import Artifact, Detection, TextSegment
from .extraction import ExtractionLimits, ExtractionOutcome, extract_artifact
from .policy import EvaluationPolicy, EvaluationRule, check_policy, load_policy
from .core.results import Report, CheckResult, Finding, Severity, PROMPT_VERSION
from .checks.verify import judge_trajectory, extract_claims, grounded_verifier, verify_claims
from .checks.judge_baseline import naive_judge, JudgeVerdict
from .checks.tool_use import check_tool_use
from .checks.injection import (
    POSSIBLE_INJECTION_THRESHOLD,
    RegexDetector,
    RegexPattern,
    check_injection,
    load_regex_detector,
)
from .checks.role import check_role_adherence
from .scoring.report import evaluate
from .adapters.langgraph import from_langgraph_messages
from .core.stats import wilson_interval, difference_is_real, Proportion
from .core.llm import providers as list_providers, list_models, default_model
from .api import Attest
from . import content, providers, results, trajectory

__all__ = [
    "Attest",
    "list_providers", "list_models", "default_model",
    "Trajectory", "Step", "ToolCall", "Artifact", "Detection", "TextSegment",
    "ExtractionLimits", "ExtractionOutcome", "extract_artifact",
    "EvaluationPolicy", "EvaluationRule", "check_policy", "load_policy",
    "Report", "CheckResult", "Finding", "Severity", "PROMPT_VERSION",
    "judge_trajectory", "extract_claims", "grounded_verifier", "verify_claims",
    "naive_judge", "JudgeVerdict",
    "check_tool_use", "check_injection", "RegexDetector", "RegexPattern", "load_regex_detector",
    "POSSIBLE_INJECTION_THRESHOLD",
    "check_role_adherence",
    "evaluate",
    "from_langgraph_messages",
    "wilson_interval", "difference_is_real", "Proportion",
]

__version__ = "0.7.0"
