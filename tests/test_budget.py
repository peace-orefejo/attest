"""Spend controls: usage accounting, hard budgets, vote early-exit, and the disk cache."""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from typer.testing import CliRunner

import attest.api as api
import attest.llm as llm_pkg
import attest.llm.structured as llm
from attest import Attest, Budget, BudgetExceeded, DiskCache, Usage
from attest.checks.verify import ClaimsOut, _BatchOut, _ClaimVerdict, verify_claims
from attest.cli import app
from attest.llm.budget import metering
from attest.llm.usage import TokenCounts, token_counts
from attest.trajectory import Step, ToolCall, Trajectory


class _V(BaseModel):
    verdict: str


class _MeteredClient:
    def __init__(self, verdicts=None, input_tokens=100, output_tokens=20):
        self.verdicts = iter(verdicts or [])
        self.calls = 0
        self.usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)

    def create_with_completion(self, *, response_model, **kwargs):
        self.calls += 1
        return self._respond(response_model), SimpleNamespace(usage=self.usage)

    def _respond(self, model):
        if model is ClaimsOut:
            return ClaimsOut(claims=["Paris is in France"])
        if model is _BatchOut:
            return _BatchOut(verdicts=[_ClaimVerdict(claim=1, verdict="supported")])
        return model(verdict=next(self.verdicts, "x"))


def _traj() -> Trajectory:
    return Trajectory(
        task="where is paris",
        steps=[Step(tool_call=ToolCall(name="search", arguments={}, output="Paris, France"))],
        final_answer="Paris is in France.",
    )


def test_usage_records_calls_and_tokens():
    client = _MeteredClient()
    usage = Usage()
    with metering(usage):
        llm.call(system="s", user="u", output=_V, client=client)
        llm.call(system="s", user="u", output=_V, client=client)
    assert usage.calls == 2
    assert usage.input_tokens == 200
    assert usage.output_tokens == 40
    assert usage.tokens == 240


def test_call_budget_fails_closed_before_spending():
    client = _MeteredClient()
    with metering(Usage(), Budget(max_calls=1)):
        llm.call(system="s", user="u", output=_V, client=client)
        with pytest.raises(BudgetExceeded, match="Call budget"):
            llm.call(system="s", user="u", output=_V, client=client)
    assert client.calls == 1


def test_token_budget_blocks_an_oversized_prompt():
    client = _MeteredClient()
    with metering(Usage(), Budget(max_tokens=50)):
        with pytest.raises(BudgetExceeded, match="Token budget"):
            llm.call(system="s", user="x" * 1000, output=_V, client=client)
    assert client.calls == 0


def test_cache_hits_are_counted_and_free():
    client = _MeteredClient()
    usage = Usage()
    with metering(usage, Budget(max_calls=1)), llm_pkg.using_cache({}):
        llm.call(system="s", user="u", output=_V, client=client)
        llm.call(system="s", user="u", output=_V, client=client)
    assert usage.calls == 1
    assert usage.cache_hits == 1


def test_budget_exceeded_is_not_swallowed_by_batch_verify(monkeypatch):
    def over(**kwargs):
        raise BudgetExceeded("over")

    monkeypatch.setattr("attest.checks.verify.call", over)
    with pytest.raises(BudgetExceeded):
        verify_claims(["a claim"], "some evidence")


def test_vote_stops_once_majority_is_decided():
    client = _MeteredClient(verdicts=["a", "a", "b"])
    out = llm.vote(
        system="s", user="u", output=_V, key=lambda o: o.verdict, samples=3, client=client
    )
    assert out.verdict == "a"
    assert client.calls == 2


def test_vote_takes_the_tiebreak_sample_on_disagreement():
    client = _MeteredClient(verdicts=["a", "b", "b"])
    out = llm.vote(
        system="s", user="u", output=_V, key=lambda o: o.verdict, samples=3, client=client
    )
    assert out.verdict == "b"
    assert client.calls == 3


def test_token_counts_normalizes_providers():
    anthropic = SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=4,
            cache_read_input_tokens=900,
            cache_creation_input_tokens=0,
        )
    )
    openai = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=7,
            completion_tokens=3,
            prompt_tokens_details=SimpleNamespace(cached_tokens=5),
        )
    )
    gemini = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=5, candidates_token_count=2, cached_content_token_count=None
        )
    )
    assert token_counts(anthropic) == TokenCounts(input=910, output=4, cached=900)
    assert token_counts(openai) == TokenCounts(input=7, output=3, cached=5)
    assert token_counts(gemini) == TokenCounts(input=5, output=2)
    assert token_counts(SimpleNamespace()) == TokenCounts()


def test_disk_cache_persists_across_instances(tmp_path):
    first = _MeteredClient()
    with llm_pkg.using_cache(DiskCache(tmp_path, provider="anthropic", model="m")):
        llm.call(system="s", user="u", output=_V, client=first)
    second = _MeteredClient()
    with llm_pkg.using_cache(DiskCache(tmp_path, provider="anthropic", model="m")):
        out = llm.call(system="s", user="u", output=_V, client=second)
    assert isinstance(out, _V)
    assert second.calls == 0


def test_disk_cache_is_scoped_by_model(tmp_path):
    a = DiskCache(tmp_path, provider="anthropic", model="m1")
    b = DiskCache(tmp_path, provider="anthropic", model="m2")
    a["k"] = _V(verdict="x")
    assert "k" in a
    assert "k" not in b


def test_attest_reports_usage_per_evaluation():
    client = _MeteredClient()
    judge = Attest(client=client)
    report = judge.evaluate(_traj())
    assert report.metadata["usage"]["calls"] == 2
    assert judge.usage.calls == 2
    again = judge.evaluate(_traj())
    assert again.metadata["usage"]["calls"] == 2
    assert judge.usage.calls == 4


def test_attest_path_cache_builds_a_disk_cache(tmp_path):
    assert isinstance(Attest(cache=tmp_path)._cache, DiskCache)


def test_cli_run_stops_at_the_call_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    client = _MeteredClient()
    monkeypatch.setattr(api, "build_client", lambda *a, **k: client)
    path = tmp_path / "runs.jsonl"
    line = _traj().model_dump_json()
    path.write_text(f"{line}\n{line}\n")

    result = CliRunner().invoke(app, ["run", str(path), "--json", "--max-calls", "3"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert len(payload["trajectories"]) == 1
    assert payload["usage"]["calls"] == 3
    assert "Call budget" in payload["budget_exceeded"]


class _Capturing(_MeteredClient):
    def __init__(self, provider=None, **kw):
        super().__init__(**kw)
        self.provider = provider
        self.users = []

    def create_with_completion(self, *, response_model, messages, **kwargs):
        self.users.append(messages[1]["content"])
        return super().create_with_completion(response_model=response_model)


def test_anthropic_gets_a_breakpoint_on_the_shared_prefix():
    import instructor

    client = _Capturing(provider=instructor.Provider.ANTHROPIC)
    llm.call(system="s", prefix="EVIDENCE", user="claims", output=_V, client=client, reuse="prefix")
    first, tail = client.users[0]
    assert first == {"type": "text", "text": "EVIDENCE", "cache_control": {"type": "ephemeral"}}
    assert tail == {"type": "text", "text": "claims"}


def test_anthropic_vote_caches_the_full_prompt():
    import instructor

    client = _Capturing(provider=instructor.Provider.ANTHROPIC, verdicts=["a", "a"])
    llm.vote(system="s", user="u", output=_V, key=lambda o: o.verdict, samples=3, client=client)
    assert client.users[0][-1]["cache_control"] == {"type": "ephemeral"}


def test_single_use_prompts_get_no_breakpoint():
    import instructor

    client = _Capturing(provider=instructor.Provider.ANTHROPIC)
    llm.call(system="s", prefix="EVIDENCE", user="claims", output=_V, client=client)
    assert client.users[0] == "EVIDENCE\n\nclaims"


def test_other_providers_get_the_prefix_first_as_plain_text():
    import instructor

    client = _Capturing(provider=instructor.Provider.GENAI)
    llm.call(system="s", prefix="EVIDENCE", user="claims", output=_V, client=client, reuse="prefix")
    assert client.users[0] == "EVIDENCE\n\nclaims"


def test_multi_batch_verify_shares_the_evidence_prefix(monkeypatch):
    seen = []

    def fake_call(**kwargs):
        seen.append(kwargs)
        return _BatchOut(verdicts=[])

    monkeypatch.setattr("attest.checks.verify.call", fake_call)
    verify_claims([f"c{i}" for i in range(4)], "the evidence", batch_size=2)
    assert len(seen) == 2
    assert all(k["reuse"] == "prefix" and "the evidence" in k["prefix"] for k in seen)
    assert seen[0]["prefix"] == seen[1]["prefix"]
