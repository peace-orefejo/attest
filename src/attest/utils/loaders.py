"""JSON and YAML loaders that reject duplicate keys instead of silently keeping the last one."""

from __future__ import annotations

import json
from collections.abc import Hashable, Iterable

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, ScalarNode


class DuplicateKeyError(ValueError):
    pass


def load_json_strict(raw: str) -> object:
    return json.loads(raw, object_pairs_hook=_unique_json_object)


def load_yaml_strict(raw: str) -> object:
    return yaml.load(raw, Loader=_UniqueKeyLoader)


def _unique_json_object(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
    mapping: dict[str, object] = {}
    for key, value in pairs:
        if key in mapping:
            raise DuplicateKeyError(f"found duplicate key {key!r}")
        mapping[key] = value
    return mapping


class _UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, object]:
        self._reject_duplicate_scalar_keys(node)
        return super().construct_mapping(node, deep=deep)

    def _reject_duplicate_scalar_keys(self, node: MappingNode) -> None:
        seen: set[Hashable] = set()
        for key_node, _ in node.value:
            if not isinstance(key_node, ScalarNode) or key_node.tag == _MERGE_TAG:
                continue
            key = _resolved_key(key_node, self)
            if key in seen:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key_node.value!r}",
                    key_node.start_mark,
                )
            seen.add(key)


_MERGE_TAG = "tag:yaml.org,2002:merge"


def _resolved_key(node: ScalarNode, loader: yaml.SafeLoader) -> Hashable:
    value: object = loader.construct_object(node)
    if isinstance(value, Hashable):
        return value
    return (node.tag, str(node.value))
