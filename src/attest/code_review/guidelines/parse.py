"""Read review rules out of a markdown file: each list item is a rule, under its nearest heading."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Guideline, ReviewGuidelines

MAX_RULES = 200
MAX_RULE_CHARS = 1_000

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.*)$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_BREAK = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_EMPHASIS = re.compile(r"(?<![\w*])(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?![\w*])")


@dataclass
class _Draft:
    section: str
    indent: int
    parts: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    parts = _CODE_SPAN.split(text)
    pieces: list[str] = []
    for index in range(0, len(parts), 3):
        pieces.append(_EMPHASIS.sub(r"\2", parts[index]))
        if index + 2 < len(parts):
            pieces.append(parts[index + 2])
    return re.sub(r"\s+", " ", "".join(pieces)).strip()


def _finish(drafts: list[_Draft], source: str) -> list[Guideline]:
    rules: list[Guideline] = []
    for draft in drafts:
        text = _clean(" ".join(draft.parts))[:MAX_RULE_CHARS]
        if text:
            rules.append(Guideline(id="", text=text, section=draft.section, source=source))
    return rules


def _parse(markdown: str) -> tuple[list[_Draft], list[_Draft]]:
    items: list[_Draft] = []
    paragraphs: list[_Draft] = []
    section = ""
    current: _Draft | None = None
    paragraph: _Draft | None = None
    fence: str | None = None
    after_blank = False
    for line in _COMMENT.sub("", markdown).splitlines():
        marker = _FENCE.match(line)
        if fence is not None:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
            elif current is not None:
                current.parts.append(line.strip())
            continue
        if marker:
            fence = marker.group(1)
            continue
        if not line.strip():
            paragraph = None
            after_blank = True
            continue
        if _BREAK.match(line):
            current, paragraph = None, None
            continue
        was_blank, after_blank = after_blank, False
        heading = _HEADING.match(line)
        if heading:
            section, current, paragraph = _clean(heading.group(1)), None, None
            continue
        item = _ITEM.match(line)
        if item:
            indent = len(item.group(1).expandtabs(4))
            if current is not None and indent > current.indent:
                current.parts.append(item.group(2))
            else:
                current = _Draft(section, indent, [item.group(2)])
                items.append(current)
            paragraph = None
            continue
        if current is not None and (line.startswith((" ", "\t")) or not was_blank):
            current.parts.append(line.strip())
            continue
        current = None
        if paragraph is None:
            paragraph = _Draft(section, 0)
            paragraphs.append(paragraph)
        paragraph.parts.append(line.strip())
    return items, paragraphs


def parse_guidelines(markdown: str, name: str = "guidelines") -> ReviewGuidelines:
    """Turn a markdown review guide into numbered rules.

    List items are rules, and indented sub-items belong to the item above them. A file with no
    list items uses each paragraph as a rule instead.
    """
    items, paragraphs = _parse(markdown)
    rules = _finish(items or paragraphs, name)[:MAX_RULES]
    if not rules:
        raise ValueError(f"No review rules found in {name}. Write each rule as a list item.")
    numbered = [rule.model_copy(update={"id": f"G{i}"}) for i, rule in enumerate(rules, 1)]
    return ReviewGuidelines(name=name, rules=numbered)
