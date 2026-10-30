from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..utils.loaders import DuplicateKeyError, load_json_strict, load_yaml_strict


def read_policy_data(source: Path) -> object:
    try:
        raw = source.read_text()
        return _parse(raw, json_format=source.suffix.lower() == ".json")
    except (OSError, json.JSONDecodeError, yaml.YAMLError, DuplicateKeyError) as exc:
        raise ValueError(f"Could not load evaluation policy {source}: {exc}") from exc


def _parse(raw: str, *, json_format: bool) -> object:
    if json_format:
        return load_json_strict(raw)
    return load_yaml_strict(raw)
