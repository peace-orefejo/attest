"""The labelling page: one HTML document with its CSS and JavaScript inlined, loading nothing.

The page, style and scripts live beside this module (`label_ui.html`, `label_ui.css`,
`label_ui.js`, `label_ui_form.js`) and are read for each page load. The Content-Security-Policy
lets the page run only its own inline script and style (by nonce) and talk only to this server.
"""

from __future__ import annotations

from pathlib import Path

ASSETS = Path(__file__).resolve().parent


def page(nonce: str) -> str:
    """The page, with its style and script inlined under `nonce`."""
    template = (ASSETS / "label_ui.html").read_text(encoding="utf-8")
    style = (ASSETS / "label_ui.css").read_text(encoding="utf-8")
    script = "\n".join(
        (ASSETS / name).read_text(encoding="utf-8") for name in ("label_ui.js", "label_ui_form.js")
    )
    return (
        template.replace("/*STYLE*/", style)
        .replace("/*SCRIPT*/", script)
        .replace("{{NONCE}}", nonce)
    )


def content_security_policy(nonce: str) -> str:
    return "; ".join(
        [
            "default-src 'none'",
            f"script-src 'nonce-{nonce}'",
            f"style-src 'nonce-{nonce}'",
            "connect-src 'self'",
            "img-src data:",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
        ]
    )
