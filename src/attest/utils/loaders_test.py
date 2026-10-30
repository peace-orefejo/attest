"""Duplicate-key-rejecting JSON and YAML loaders."""

import pytest
import yaml

from attest.utils.loaders import DuplicateKeyError, load_json_strict, load_yaml_strict


def test_json_loader_accepts_unique_keys_and_rejects_duplicates():
    assert load_json_strict('{"a": {"b": 1}}') == {"a": {"b": 1}}
    with pytest.raises(DuplicateKeyError, match="duplicate key 'b'"):
        load_json_strict('{"a": {"b": 1, "b": 2}}')


def test_yaml_loader_accepts_unique_keys_and_rejects_duplicates():
    assert load_yaml_strict("a:\n  b: 1\n") == {"a": {"b": 1}}
    with pytest.raises(yaml.YAMLError, match="duplicate key 'b'"):
        load_yaml_strict("a:\n  b: 1\n  b: 2\n")


def test_yaml_loader_stays_safe():
    with pytest.raises(yaml.YAMLError):
        load_yaml_strict("!!python/object/apply:os.system ['true']")


@pytest.mark.parametrize("raw", ["true: 1\nTrue: 2\n", "1: a\n0x1: b\n", "1: a\ntrue: b\n"])
def test_yaml_loader_rejects_keys_that_resolve_to_the_same_value(raw):
    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        load_yaml_strict(raw)


def test_yaml_loader_keeps_distinct_typed_keys_and_merges():
    assert load_yaml_strict('1: a\n"1": b\n') == {1: "a", "1": "b"}
    merged = load_yaml_strict("base: &b {x: 1}\nm:\n  <<: *b\n  y: 2\n")
    assert merged == {"base": {"x": 1}, "m": {"x": 1, "y": 2}}
