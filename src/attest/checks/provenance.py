"""Point each faithfulness finding at the one evidence block its quote came from."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from ..prompts.evidence import escape_block_tags
from ..results import Finding
from ..trajectory import EvidenceBlock


class _SearchableBlock(BaseModel):
    location: str
    plain: str
    escaped: str

    def contains(self, needle: str) -> bool:
        return needle in self.plain or needle in self.escaped


def with_locations(findings: Sequence[Finding], blocks: Sequence[EvidenceBlock]) -> list[Finding]:
    """Add `metadata["location"]` to findings whose quote appears in exactly one block."""
    searchable = [_searchable(block) for block in blocks]
    located: list[Finding] = []
    for finding in findings:
        location = _locate(finding.evidence, searchable)
        if location is None:
            located.append(finding)
            continue
        located.append(
            finding.model_copy(update={"metadata": {**finding.metadata, "location": location}})
        )
    return located


def _locate(quote: str | None, searchable: list[_SearchableBlock]) -> str | None:
    needle = _normalize(quote or "")
    if not needle:
        return None
    matches = [block.location for block in searchable if block.contains(needle)]
    return matches[0] if len(matches) == 1 else None


def _searchable(block: EvidenceBlock) -> _SearchableBlock:
    return _SearchableBlock(
        location=block.location,
        plain=_normalize(block.text),
        escaped=_normalize(escape_block_tags(block.text)),
    )


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()
