from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from .files import read_policy_data

RuleKind = Literal[
    "rubric",
    "evidence",
    "required_text",
    "forbidden_text",
    "required_tools",
    "required_tool_order",
    "allowed_tools",
]
RuleSeverity = Literal["warn", "fail"]

DETERMINISTIC_KINDS: frozenset[str] = frozenset(
    {"required_text", "forbidden_text", "required_tools", "required_tool_order", "allowed_tools"}
)
SEMANTIC_KINDS: frozenset[str] = frozenset({"rubric", "evidence"})
MAX_RULE_VALUES = 200


class EvaluationRule(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=8_000)
    kind: RuleKind = "rubric"
    severity: RuleSeverity = "fail"
    values: tuple[str, ...] = ()
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _validate_values(self) -> EvaluationRule:
        if self.kind in DETERMINISTIC_KINDS and not self.values:
            raise ValueError(f"Rule {self.id!r} of kind {self.kind!r} requires values.")
        if any(not value.strip() for value in self.values):
            raise ValueError(f"Rule {self.id!r} values cannot be empty or whitespace-only.")
        if len(self.values) > MAX_RULE_VALUES:
            raise ValueError(f"Rule {self.id!r} cannot contain more than 200 values.")
        return self

    @property
    def needs_llm(self) -> bool:
        return self.kind in SEMANTIC_KINDS


class EvaluationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1.0", min_length=1, max_length=100)
    description: str = ""
    rules: tuple[EvaluationRule, ...]

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> EvaluationPolicy:
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Policy rule ids must be unique.")
        if not ids:
            raise ValueError("A policy requires at least one rule.")
        return self

    @computed_field
    @property
    def hash(self) -> str:
        payload = self.model_dump_json(exclude={"hash"}, exclude_none=True)
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()

    @property
    def needs_llm(self) -> bool:
        return any(rule.needs_llm for rule in self.rules)

    @classmethod
    def from_file(cls, path: str | Path) -> EvaluationPolicy:
        """Load a policy from a JSON or YAML file, rejecting duplicate keys."""
        return cls.model_validate(read_policy_data(Path(path)))
