"""Per-format parsers that yield ``(source_kind, text)`` parts from raw bytes."""

from .csv_text import csv_parts
from .html_text import html_parts
from .image_text import image_parts
from .json_text import json_parts
from .pdf_text import pdf_parts
from .xml_text import xml_parts

__all__ = ["csv_parts", "html_parts", "image_parts", "json_parts", "pdf_parts", "xml_parts"]
