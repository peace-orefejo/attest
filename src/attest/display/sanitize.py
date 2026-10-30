from __future__ import annotations

import re

_UNSAFE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def terminal_safe(text: str) -> str:
    """Show control and bidi characters as escapes so untrusted text cannot drive the terminal."""
    return _UNSAFE.sub(_escape, text)


def _escape(match: re.Match[str]) -> str:
    code = ord(match.group())
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"
