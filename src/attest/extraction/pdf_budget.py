from __future__ import annotations

from pypdf.generic import DictionaryObject

from .pdf_filters import decode_stream_bounded
from .pdf_objects import as_object_list, require_dictionary, require_stream, resolve


class PdfDecodeBudget:
    """Bound content, font maps, and form streams read by pypdf text extraction."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0
        self.seen: set[int] = set()

    def charge_page(self, page: DictionaryObject) -> None:
        self._charge_streams(page.get("/Contents"))
        self._charge_resources(page.get("/Resources"))

    def _charge_resources(self, resources_ref: object) -> None:
        if resources_ref is None:
            return
        resources = require_dictionary(resolve(resources_ref))
        self._charge_fonts(resources.get("/Font"))
        self._charge_form_xobjects(resources.get("/XObject"))

    def _charge_fonts(self, fonts_ref: object) -> None:
        if fonts_ref is None:
            return
        for font_ref in require_dictionary(resolve(fonts_ref)).values():
            font = require_dictionary(resolve(font_ref))
            self._charge_streams(font.get("/ToUnicode"))

    def _charge_form_xobjects(self, xobjects_ref: object) -> None:
        if xobjects_ref is None:
            return
        for xobject_ref in require_dictionary(resolve(xobjects_ref)).values():
            xobject = require_dictionary(resolve(xobject_ref))
            if str(xobject.get("/Subtype")) != "/Form":
                continue
            self._charge_streams(xobject)
            self._charge_resources(xobject.get("/Resources"))

    def _charge_streams(self, value: object) -> None:
        if value is None:
            return
        resolved = resolve(value)
        items = as_object_list(resolved)
        if items is not None:
            for item in items:
                self._charge_streams(item)
            return
        identity = id(resolved)
        if identity in self.seen:
            return
        self.seen.add(identity)
        remaining = self.limit - self.used
        if remaining < 0:
            raise ValueError(f"PDF decoded content exceeds {self.limit} byte limit")
        self.used += len(decode_stream_bounded(require_stream(resolved), remaining, self.limit))
