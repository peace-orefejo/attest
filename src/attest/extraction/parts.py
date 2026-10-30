from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field, SkipValidation


class ExtractedPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_kind: str
    text: str


class ParsedParts(BaseModel):
    parts: SkipValidation[Iterable[ExtractedPart]]
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list[str])
