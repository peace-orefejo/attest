"""The evaluation policy model: a named, versioned, hashed set of rules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from ..utils.strict_parsing import DuplicateKeyError, load_json_unique, load_yaml_unique
from .rule import EvaluationRule


class EvaluationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1.0", min_length=1, max_length=100)
    description: str = ""
    rules: tuple[EvaluationRule, ...]

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> "EvaluationPolicy":
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
    def from_file(cls, path: str | Path) -> "EvaluationPolicy":
        source = Path(path)
        try:
            raw = source.read_text()
            data = (load_json_unique(raw) if source.suffix.lower() == ".json"
                    else load_yaml_unique(raw))
        except (OSError, json.JSONDecodeError, yaml.YAMLError, DuplicateKeyError) as exc:
            raise ValueError(f"Could not load evaluation policy {source}: {exc}") from exc
        return cls.model_validate(data)


PolicyInput = EvaluationPolicy | dict | str | Path | None
