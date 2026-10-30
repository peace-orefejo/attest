from __future__ import annotations

from pathlib import Path

from .models import EvaluationPolicy, EvaluationRule

PolicyInput = EvaluationPolicy | dict[str, object] | str | Path | None

_POLICY_FILE_SUFFIXES = frozenset({".json", ".yaml", ".yml"})


def load_policy(value: PolicyInput) -> EvaluationPolicy | None:
    """Normalize a policy object, mapping, file path, or plain-text rubric into a policy."""
    if value is None:
        return None
    if isinstance(value, EvaluationPolicy):
        return value.model_copy(deep=True)
    if isinstance(value, dict):
        return EvaluationPolicy.model_validate(value)
    if isinstance(value, Path):
        return EvaluationPolicy.from_file(value)
    if Path(value).suffix.lower() in _POLICY_FILE_SUFFIXES:
        return EvaluationPolicy.from_file(value)
    return _prompt_policy(value)


def _prompt_policy(value: str) -> EvaluationPolicy:
    prompt = value.strip()
    if not prompt:
        raise ValueError("Policy prompt cannot be empty.")
    return EvaluationPolicy(
        name="custom-policy",
        rules=(EvaluationRule(id="custom-policy", description=prompt, kind="rubric"),),
    )
