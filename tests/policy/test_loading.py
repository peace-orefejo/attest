"""Loading policies from files, mappings and plain prompts."""

import json

import pytest

from attest import Attest, EvaluationPolicy

from ._helpers import _deterministic_policy, _traj


def test_yaml_policy_loaded_once(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("""
name: finance
version: "1.4"
rules:
  - id: disclaimer
    description: Include the disclaimer.
    kind: required_text
    severity: warn
    values: ["not financial advice"]
""")
    judge = Attest(policy=path)
    path.unlink()
    result = judge.policy_check(_traj())
    assert result.findings[0].severity.value == "warn"
    assert result.passed is True


def test_dict_policy_and_hash_are_stable():
    raw = _deterministic_policy().model_dump(exclude={"hash"})
    first = Attest(policy=raw).policy
    second = Attest(policy=json.loads(json.dumps(raw))).policy
    assert first.hash == second.hash


def test_plain_string_becomes_semantic_policy_prompt():
    judge = Attest(policy="The answer must be respectful and concise.")
    assert judge.policy.name == "custom-policy"
    assert judge.policy.rules[0].kind == "rubric"

def test_yaml_duplicate_keys_are_rejected(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("""
name: support
rules:
  - id: privacy
    description: Protect customer data.
    severity: fail
    severity: warn
""")
    with pytest.raises(ValueError, match="duplicate key 'severity'"):
        EvaluationPolicy.from_file(path)


def test_json_duplicate_keys_are_rejected(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(
        '{"name":"support","rules":[{"id":"privacy","description":"Protect data",'
        '"severity":"fail","severity":"warn"}]}'
    )
    with pytest.raises(ValueError, match="duplicate key 'severity'"):
        EvaluationPolicy.from_file(path)


def test_existing_non_policy_filename_remains_a_plain_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("not a policy")
    policy = Attest(policy="README.md").policy
    assert policy.rules[0].description == "README.md"
