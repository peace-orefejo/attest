"""Duplicate-key-rejecting JSON and YAML loaders."""

import pytest
import yaml

from attest.utils import DuplicateKeyError, load_json_unique, load_yaml_unique


def test_json_loader_accepts_unique_keys_and_rejects_duplicates():
    assert load_json_unique('{"a": {"b": 1}}') == {"a": {"b": 1}}
    with pytest.raises(DuplicateKeyError, match="duplicate key 'b'"):
        load_json_unique('{"a": {"b": 1, "b": 2}}')


def test_yaml_loader_accepts_unique_keys_and_rejects_duplicates():
    assert load_yaml_unique("a:\n  b: 1\n") == {"a": {"b": 1}}
    with pytest.raises(yaml.YAMLError, match="duplicate key 'b'"):
        load_yaml_unique("a:\n  b: 1\n  b: 2\n")


def test_yaml_loader_stays_safe():
    with pytest.raises(yaml.YAMLError):
        load_yaml_unique("!!python/object/apply:os.system ['true']")
