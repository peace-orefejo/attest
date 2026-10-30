from __future__ import annotations

from collections.abc import Iterator
from html.parser import HTMLParser
from xml.etree.ElementTree import Element

from .parts import ExtractedPart, ParsedParts

_TEXT_ATTRIBUTES = {"alt", "title", "aria-label"}


class _HTMLText(HTMLParser):
    def __init__(self, max_chars: int) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[ExtractedPart] = []
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
        self.parts.append(ExtractedPart(source_kind=source_kind, text=clipped))
        self.used += len(clipped)
        self.truncated |= len(clipped) < len(value)

    def handle_data(self, data: str) -> None:
        self._append("html.text", data)

    def handle_comment(self, data: str) -> None:
        self._append("html.comment", data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value and name.lower() in _TEXT_ATTRIBUTES:
                self._append(f"html.attribute.{name}", value)


def html_parts(raw: bytes, max_chars: int) -> ParsedParts:
    parser = _HTMLText(max_chars)
    parser.feed(raw.decode("utf-8", errors="replace"))
    return ParsedParts(parts=parser.parts, truncated=parser.truncated)


def xml_parts(raw: bytes) -> ParsedParts:
    from defusedxml import ElementTree

    root = ElementTree.fromstring(raw)
    return ParsedParts(parts=_xml_element_parts(root))


def _xml_element_parts(root: Element) -> Iterator[ExtractedPart]:
    for index, element in enumerate(root.iter()):
        if element.text and element.text.strip():
            yield ExtractedPart(source_kind=f"xml.element[{index}].text", text=element.text)
        for name, value in element.attrib.items():
            yield ExtractedPart(source_kind=f"xml.element[{index}].attribute.{name}", text=value)
