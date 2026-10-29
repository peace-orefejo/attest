from __future__ import annotations

import html


def escape_markup(text: str) -> str:
    """Neutralize `<` and `>` so untrusted text cannot close a structural prompt wrapper."""
    return html.escape(text, quote=False)
