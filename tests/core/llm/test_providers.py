"""Provider registry — all offline (live fetch tested with faked SDK clients)."""

import sys
import types

import pytest

from attest.core.llm.catalog import _gemini_chat_models, fetch_models, list_models
from attest.core.llm.clients import build_client
from attest.core.llm.env import load_env, resolve_key
from attest.core.llm.providers import curated_models, default_model, providers


def test_registry_basics():
    assert set(providers()) == {"anthropic", "openai", "gemini"}
    assert default_model("anthropic") == "claude-haiku-4-5"
    for prov in providers():
        assert curated_models(prov)


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        default_model("bogus")


def test_resolve_key_prefers_argument_then_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert resolve_key("anthropic", "explicit") == "explicit"
    assert resolve_key("anthropic") is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert resolve_key("anthropic") == "from-env"


def test_gemini_falls_back_to_google_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
    assert resolve_key("gemini") == "g-key"


def test_list_models_without_key_is_curated(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert list_models("openai") == curated_models("openai")


def test_list_models_with_key_goes_live(monkeypatch):
    _install_fake_sdk(monkeypatch, "openai", "OpenAI",
                      [_Model(id="gpt-live")])
    assert list_models("openai", key="k") == ["gpt-live"]


def test_build_client_anthropic_no_network():
    client = build_client("anthropic", "claude-haiku-4-5", key="sk-ant-fake")
    assert client is not None


class _Model:
    def __init__(self, id=None, name=None, supported_actions=None):
        self.id = id
        self.name = name
        self.supported_actions = supported_actions


class _FakeSDK:
    instances = []

    def __init__(self, *, api_key, items):
        self.api_key = api_key
        self.models = types.SimpleNamespace(list=lambda: items)
        _FakeSDK.instances.append(self)


def _install_fake_sdk(monkeypatch, module_path, cls_name, items):
    captured = {}

    def factory(*, api_key):
        captured["api_key"] = api_key
        return _FakeSDK(api_key=api_key, items=items)

    mod = types.ModuleType(module_path)
    setattr(mod, cls_name, factory)
    monkeypatch.setitem(sys.modules, module_path, mod)
    return captured


def test_fetch_anthropic_returns_ids(monkeypatch):
    captured = _install_fake_sdk(monkeypatch, "anthropic", "Anthropic",
                                 [_Model(id="claude-x"), _Model(id="claude-y")])
    assert fetch_models("anthropic", key="k") == ["claude-x", "claude-y"]
    assert captured["api_key"] == "k"


def test_fetch_openai_sorts_ids(monkeypatch):
    _install_fake_sdk(monkeypatch, "openai", "OpenAI",
                      [_Model(id="gpt-z"), _Model(id="gpt-a")])
    assert fetch_models("openai", key="k") == ["gpt-a", "gpt-z"]


def test_gemini_filters_chat_models_and_strips_prefix():
    models = [
        _Model(name="models/gemini-2.0-flash", supported_actions=["generateContent"]),
        _Model(name="models/embedding-001", supported_actions=["embedContent"]),
        _Model(name="models/gemini-legacy", supported_actions=None),
    ]
    assert _gemini_chat_models(models) == ["gemini-2.0-flash", "gemini-legacy"]


def test_fetch_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        fetch_models("openai")


@pytest.fixture
def real_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder")
    monkeypatch.setattr("attest.core.llm.env.load_env", load_env)
    load_env.cache_clear()
    yield
    load_env.cache_clear()


def test_resolve_key_reads_dotenv_from_working_directory(real_dotenv, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert resolve_key("anthropic") == "from-dotenv"


def test_dotenv_does_not_override_real_env(real_dotenv, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert resolve_key("anthropic") == "from-env"


class _Parsed:
    def __init__(self, parsed_output, stop_reason="end_turn"):
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, result):
        self.result = result
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.result


def _anthropic_client(model, result):
    from attest.core.llm.clients import AnthropicClient

    client = AnthropicClient(model, api_key="sk-ant-fake")
    fake = _FakeMessages(result)
    client.client = types.SimpleNamespace(messages=fake)
    return client, fake


def _messages():
    return [{"role": "system", "content": "judge"}, {"role": "user", "content": "claim"}]


def test_anthropic_client_uses_structured_outputs_without_tool_choice():
    from attest.checks.verify import VerdictOut

    out = VerdictOut(verdict="supported")
    client, fake = _anthropic_client("claude-sonnet-5-5", _Parsed(out))
    got = client.create(response_model=VerdictOut, messages=_messages(), max_tokens=64,
                        temperature=0)
    assert got is out
    assert fake.kwargs["output_format"] is VerdictOut
    assert fake.kwargs["system"] == "judge"
    assert fake.kwargs["messages"] == [{"role": "user", "content": "claim"}]
    assert "tool_choice" not in fake.kwargs and "tools" not in fake.kwargs
    assert "temperature" not in fake.kwargs and "extra_body" not in fake.kwargs


def test_anthropic_client_keeps_temperature_for_models_that_accept_it():
    from attest.checks.verify import VerdictOut

    client, fake = _anthropic_client("claude-haiku-4-5", _Parsed(VerdictOut(verdict="supported")))
    client.create(response_model=VerdictOut, messages=_messages(), max_tokens=64, temperature=0)
    assert "temperature" not in fake.kwargs
    assert fake.kwargs["extra_body"] == {"temperature": 0}


@pytest.mark.parametrize("model", ["claude-opus-4-8", "claude-opus-5", "claude-haiku-5-5"])
def test_anthropic_client_drops_temperature_for_newer_models(model):
    from attest.checks.verify import VerdictOut

    client, fake = _anthropic_client(model, _Parsed(VerdictOut(verdict="supported")))
    client.create(response_model=VerdictOut, messages=_messages(), max_tokens=64, temperature=0)
    assert "extra_body" not in fake.kwargs


def test_anthropic_client_raises_when_no_structured_output():
    from attest.checks.verify import VerdictOut

    client, _ = _anthropic_client("claude-opus-5-5", _Parsed(None, stop_reason="max_tokens"))
    with pytest.raises(RuntimeError, match="max_tokens"):
        client.create(response_model=VerdictOut, messages=_messages(), max_tokens=64)
