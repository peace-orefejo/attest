"""HTML visible text, comments, and descriptive attributes under a character budget."""

from __future__ import annotations

from html.parser import HTMLParser


class _HTMLText(HTMLParser):
    def __init__(self, max_chars: int) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[tuple[str, str]] = []
        self.max_chars = max_chars
        self.used = 0
        self.truncated = False

    def _append(self, source_kind: str, value: str) -> None:
        if not value.strip():
            return
        remaining = self.max_chars - self.used
        if remaining <= 0:
            self.truncated = True
            return
        clipped = value[:remaining]
        self.parts.append((source_kind, clipped))
        self.used += len(clipped)
        self.truncated |= len(clipped) < len(value)

    def handle_data(self, data: str) -> None:
        self._append("html.text", data)

    def handle_comment(self, data: str) -> None:
        self._append("html.comment", data)

    def handle_starttag(self, tag: str, attrs) -> None:
        for name, value in attrs:
            if value and name.lower() in {"alt", "title", "aria-label"}:
                self._append(f"html.attribute.{name}", value)


def html_parts(raw: bytes, max_chars: int) -> tuple[list[tuple[str, str]], bool]:
    parser = _HTMLText(max_chars)
    parser.feed(raw.decode("utf-8", errors="replace"))
    return parser.parts, parser.truncated
