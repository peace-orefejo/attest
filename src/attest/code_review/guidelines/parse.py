"""Read review rules out of a markdown file: each list item is a rule, under its nearest heading."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .markdown import clean_inline, strip_comments
from .models import Guideline, ReviewGuidelines

MAX_RULES = 200
MAX_RULE_CHARS = 1_000
MAX_GUIDELINES_CHARS = 200_000

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.*)$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_BREAK = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_RAW_RULE_CHARS = MAX_RULE_CHARS * 4


class _Draft(BaseModel):
    section: str
    indent: int
    parts: list[str] = Field(default_factory=list[str])


class _State(BaseModel):
    items: list[_Draft] = Field(default_factory=list[_Draft])
    paragraphs: list[_Draft] = Field(default_factory=list[_Draft])
    section: str = ""
    current: _Draft | None = None
    paragraph: _Draft | None = None
    fence: str | None = None
    after_blank: bool = False


def parse_guidelines(markdown: str, name: str = "guidelines") -> ReviewGuidelines:
    """Turn a markdown review guide into numbered rules.

    List items are rules, and indented sub-items belong to the item above them. A file with no
    list items uses each paragraph as a rule instead.
    """
    if len(markdown) > MAX_GUIDELINES_CHARS:
        raise ValueError(
            f"The review rules in {name} are too long ({len(markdown)} characters; "
            f"the limit is {MAX_GUIDELINES_CHARS})."
        )
    state = _State()
    for line in strip_comments(markdown).splitlines():
        _read_line(line, state)
    rules = _finish(state.items or state.paragraphs, name)[:MAX_RULES]
    if not rules:
        raise ValueError(f"No review rules found in {name}. Write each rule as a list item.")
    numbered = [rule.model_copy(update={"id": f"G{i}"}) for i, rule in enumerate(rules, 1)]
    return ReviewGuidelines(name=name, rules=numbered)


def _read_line(line: str, state: _State) -> None:
    marker = _FENCE.match(line)
    if state.fence is not None:
        _inside_fence(line, marker, state)
        return
    if marker:
        state.fence = marker.group(1)
        return
    if not line.strip():
        state.paragraph = None
        state.after_blank = True
        return
    if _BREAK.match(line):
        state.current, state.paragraph = None, None
        return
    was_blank, state.after_blank = state.after_blank, False
    heading = _HEADING.match(line)
    if heading:
        state.section, state.current, state.paragraph = clean_inline(heading.group(1)), None, None
        return
    item = _ITEM.match(line)
    if item:
        _start_or_extend_item(item, state)
        return
    if state.current is not None and (line.startswith((" ", "\t")) or not was_blank):
        state.current.parts.append(line.strip())
        return
    _add_to_paragraph(line, state)


def _inside_fence(line: str, marker: re.Match[str] | None, state: _State) -> None:
    fence = state.fence or ""
    if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
        state.fence = None
    elif state.current is not None:
        state.current.parts.append(line.strip())


def _start_or_extend_item(item: re.Match[str], state: _State) -> None:
    indent = len(item.group(1).expandtabs(4))
    if state.current is not None and indent > state.current.indent:
        state.current.parts.append(item.group(2))
    else:
        state.current = _Draft(section=state.section, indent=indent, parts=[item.group(2)])
        state.items.append(state.current)
    state.paragraph = None


def _add_to_paragraph(line: str, state: _State) -> None:
    state.current = None
    if state.paragraph is None:
        state.paragraph = _Draft(section=state.section, indent=0)
        state.paragraphs.append(state.paragraph)
    state.paragraph.parts.append(line.strip())


def _finish(drafts: list[_Draft], source: str) -> list[Guideline]:
    rules: list[Guideline] = []
    for draft in drafts:
        raw = " ".join(draft.parts)[:_RAW_RULE_CHARS]
        text = clean_inline(raw)[:MAX_RULE_CHARS]
        if text:
            rules.append(Guideline(id="", text=text, section=draft.section, source=source))
    return rules
