"""XML element text and attributes, parsed with defusedxml."""

from __future__ import annotations

from typing import Iterable


def xml_parts(raw: bytes) -> Iterable[tuple[str, str]]:
    from defusedxml import ElementTree
    root = ElementTree.fromstring(raw)
    def parts() -> Iterable[tuple[str, str]]:
        for index, element in enumerate(root.iter()):
            if element.text and element.text.strip():
                yield (f"xml.element[{index}].text", element.text)
            for name, value in element.attrib.items():
                yield (f"xml.element[{index}].attribute.{name}", value)
    return parts()
