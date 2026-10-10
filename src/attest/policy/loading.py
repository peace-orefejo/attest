"""Turn a policy object, mapping, file path or plain prompt into an EvaluationPolicy."""

from __future__ import annotations

from pathlib import Path

from .models import EvaluationPolicy, PolicyInput
from .rule import EvaluationRule


def load_policy(value: PolicyInput) -> EvaluationPolicy | None:
    if value is None:
        return value
    if isinstance(value, EvaluationPolicy):
        return value.model_copy(deep=True)
    if isinstance(value, dict):
        return EvaluationPolicy.model_validate(value)
    if isinstance(value, Path):
        return EvaluationPolicy.from_file(value)
    candidate = Path(value)
    if candidate.suffix.lower() in {".json", ".yaml", ".yml"}:
        return EvaluationPolicy.from_file(candidate)
    prompt = str(value).strip()
    if not prompt:
        raise ValueError("Policy prompt cannot be empty.")
    return EvaluationPolicy(
        name="custom-policy",
        rules=(EvaluationRule(id="custom-policy", description=prompt, kind="rubric"),),
    )
