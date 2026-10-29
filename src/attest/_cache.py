"""A response cache on disk, so repeated runs across processes (CI, notebooks) reuse verdicts."""

from __future__ import annotations

import json
import os
import re
from collections.abc import MutableMapping
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text)


class DiskCache(MutableMapping):
    """One JSON file per judge call, namespaced by provider and model."""

    def __init__(self, root: str | os.PathLike, *, provider: str, model: str) -> None:
        self.path = Path(root) / f"{_slug(provider)}__{_slug(model)}"
        self.path.mkdir(parents=True, exist_ok=True)

    def _file(self, key: str) -> Path:
        return self.path / f"{key}.json"

    def __getitem__(self, key: str) -> dict:
        try:
            return json.loads(self._file(key).read_text())
        except (OSError, ValueError):
            raise KeyError(key) from None

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self._file(key).is_file()

    def __setitem__(self, key: str, value: BaseModel | dict) -> None:
        data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
        tmp = self._file(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        tmp.replace(self._file(key))

    def __delitem__(self, key: str) -> None:
        try:
            self._file(key).unlink()
        except FileNotFoundError:
            raise KeyError(key) from None

    def __iter__(self) -> Iterator[str]:
        return (p.stem for p in self.path.glob("*.json"))

    def __len__(self) -> int:
        return sum(1 for _ in self.path.glob("*.json"))
