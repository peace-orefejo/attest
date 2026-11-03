"""The labelling guidelines as HTML for the page's help panel, read from guidelines.md at startup.

Only the subset of Markdown guidelines.md uses is handled: headings, paragraphs, lists, tables,
quotes, code blocks, bold, code and links (shown as their text). Every piece of text is
escaped before any markup is added.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

GUIDELINES = Path(__file__).resolve().parent.parent / "annotations" / "guidelines.md"

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_ORDERED = re.compile(r"\d+\.\s")
_LABEL_CELL = re.compile(r"`([a-z_]+)`")


class HelpSection(BaseModel):
    title: str
    html: str
    definitions: dict[str, str]
    """Label -> its definition, from the section's table."""


def help_sections(path: Path = GUIDELINES) -> list[HelpSection]:
    """Each `## ` section of the guidelines, rendered, with its label definitions."""
    sections: list[HelpSection] = []
    title: str | None = None
    lines: list[str] = []
    for line in [*path.read_text(encoding="utf-8").splitlines(), "## "]:
        if line.startswith("## "):
            if title is not None:
                sections.append(_section(title, lines))
            title, lines = line[3:].strip(), []
        elif title is not None:
            lines.append(line)
    return sections


def _section(title: str, lines: list[str]) -> HelpSection:
    return HelpSection(title=title, html=render(lines), definitions=_definitions(lines))


def render(lines: list[str]) -> str:
    """Markdown lines to HTML; every piece of text is escaped first."""
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
        elif line.startswith("```"):
            end = _until(lines, index + 1, lambda text: text.startswith("```"))
            code = html.escape("\n".join(lines[index + 1 : end]))
            out.append(f"<pre><code>{code}</code></pre>")
            index = end + 1
        elif line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")) + 1, 5)
            out.append(f"<h{level}>{inline(line.lstrip('#').strip())}</h{level}>")
            index += 1
        elif line.startswith("|"):
            end = _until(lines, index, lambda text: not text.startswith("|"))
            out.append(_table(lines[index:end]))
            index = end
        else:
            end = _block_end(lines, index)
            out.append(_block(lines[index:end]))
            index = end
    return "\n".join(out)


def inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = _LINK.sub(r"\1", escaped)
    escaped = _INLINE_CODE.sub(r"<code>\1</code>", escaped)
    return _BOLD.sub(r"<strong>\1</strong>", escaped)


def _block(lines: list[str]) -> str:
    first = lines[0].lstrip()
    if first.startswith("> "):
        return f"<blockquote>{inline(' '.join(line.lstrip('> ') for line in lines))}</blockquote>"
    ordered = bool(_ORDERED.match(first))
    if ordered or first.startswith("- "):
        tag = "ol" if ordered else "ul"
        return f"<{tag}>{''.join(f'<li>{inline(item)}</li>' for item in _items(lines))}</{tag}>"
    return f"<p>{inline(' '.join(line.strip() for line in lines))}</p>"


def _items(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if line.startswith("- ") or _ORDERED.match(line):
            items.append(stripped.split(" ", 1)[1] if " " in stripped else "")
        elif items:
            items[-1] += " " + stripped
    return items


def _table(rows: list[str]) -> str:
    cells = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows]
    head, body = cells[0], [row for row in cells[1:] if not set("".join(row)) <= set("-: ")]
    header = "".join(f"<th scope='col'>{inline(cell)}</th>" for cell in head)
    rows_html = "".join(
        "<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>" for row in body
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{rows_html}</tbody></table>"


def _definitions(lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        label = _LABEL_CELL.fullmatch(cells[0]) if len(cells) > 1 else None
        if label is not None:
            found[label.group(1)] = _LINK.sub(r"\1", cells[1]).replace("`", "").replace("**", "")
    return found


def _block_end(lines: list[str], start: int) -> int:
    def ends(text: str) -> bool:
        return not text.strip() or text.startswith(("#", "|", "```"))

    return _until(lines, start + 1, ends)


def _until(lines: list[str], start: int, stop: Callable[[str], bool]) -> int:
    index = start
    while index < len(lines) and not stop(lines[index]):
        index += 1
    return index
