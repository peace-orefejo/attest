from __future__ import annotations

import re


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text)
