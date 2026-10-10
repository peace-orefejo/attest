"""JSON and YAML loaders that reject duplicate mapping keys."""

from __future__ import annotations

import json

import yaml


class DuplicateKeyError(ValueError):
    pass


def _unique_json_object(pairs):
    mapping = {}
    for key, value in pairs:
        if key in mapping:
            raise DuplicateKeyError(f"found duplicate key {key!r}")
        mapping[key] = value
    return mapping


def load_json_unique(raw: str):
    return json.loads(raw, object_pairs_hook=_unique_json_object)


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"found duplicate key {key!r}", key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_yaml_unique(raw: str):
    return yaml.load(raw, Loader=_UniqueKeyLoader)
