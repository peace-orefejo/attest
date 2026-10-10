"""A single evaluation rule and its kinds."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RuleKind = Literal[
    "rubric", "evidence", "required_text", "forbidden_text",
    "required_tools", "required_tool_order", "allowed_tools",
]
RuleSeverity = Literal["warn", "fail"]


class EvaluationRule(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=8_000)
    kind: RuleKind = "rubric"
    severity: RuleSeverity = "fail"
    values: tuple[str, ...] = ()
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _validate_values(self) -> "EvaluationRule":
        deterministic = {
            "required_text", "forbidden_text", "required_tools",
            "required_tool_order", "allowed_tools",
        }
        if self.kind in deterministic and not self.values:
            raise ValueError(f"Rule {self.id!r} of kind {self.kind!r} requires values.")
        if any(not value.strip() for value in self.values):
            raise ValueError(f"Rule {self.id!r} values cannot be empty or whitespace-only.")
        if len(self.values) > 200:
            raise ValueError(f"Rule {self.id!r} cannot contain more than 200 values.")
        return self

    @property
    def needs_llm(self) -> bool:
        return self.kind in {"rubric", "evidence"}
