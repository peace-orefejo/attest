from __future__ import annotations

from pydantic import BaseModel, Field


class Guideline(BaseModel):
    id: str
    text: str
    section: str = ""
    source: str = ""


class ReviewGuidelines(BaseModel):
    name: str
    rules: list[Guideline] = Field(default_factory=list[Guideline])
    builtin: bool = False

    def get(self, rule_id: str) -> Guideline | None:
        return next((rule for rule in self.rules if rule.id == rule_id), None)

    def render(self) -> str:
        """The rules as numbered lines, grouped under their section."""
        lines: list[str] = []
        section = None
        for rule in self.rules:
            if rule.section != section:
                section = rule.section
                if section:
                    lines.append(f"## {section}")
            lines.append(f"{rule.id}: {rule.text}")
        return "\n".join(lines)
