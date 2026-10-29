"""Response caching: re-evaluating an identical run is free, without collapsing self-consistency."""

from pydantic import BaseModel

import attest.llm as llm_pkg
import attest.llm.response_cache as response_cache_module
import attest.llm.structured as llm


class _V(BaseModel):
    verdict: str


def _counting_client(created):
    def fake_create(**kwargs):
        created["n"] += 1
        return kwargs["response_model"](verdict=f"v{created['n']}")

    class _Client:
        create = staticmethod(fake_create)

    return _Client()


def test_cache_reuses_samples_across_runs(monkeypatch):
    created = {"n": 0}
    monkeypatch.setattr(llm, "resolve_client", lambda: _counting_client(created))
    with llm_pkg.using_cache({}):
        first = [llm.call(system="s", user="u", output=_V, sample=i) for i in range(3)]
        again = [llm.call(system="s", user="u", output=_V, sample=i) for i in range(3)]
    assert created["n"] == 3
    assert [r.verdict for r in first] == [r.verdict for r in again]
    assert len({r.verdict for r in first}) == 3


def test_cache_preserves_vote_self_consistency(monkeypatch):
    created = {"n": 0}
    monkeypatch.setattr(llm, "resolve_client", lambda: _counting_client(created))
    with llm_pkg.using_cache({}):
        llm.vote(system="s", user="u", output=_V, key=lambda o: o.verdict, samples=3)
        llm.vote(system="s", user="u", output=_V, key=lambda o: o.verdict, samples=3)
    assert created["n"] == 3


def test_without_cache_every_call_hits_the_client(monkeypatch):
    created = {"n": 0}
    monkeypatch.setattr(llm, "resolve_client", lambda: _counting_client(created))
    llm.call(system="s", user="u", output=_V, sample=0)
    llm.call(system="s", user="u", output=_V, sample=0)
    assert created["n"] == 2


def test_attest_cache_flag_wires_a_store():
    from attest import Attest

    assert Attest(cache=True)._cache is not None
    assert Attest()._cache is None
    assert Attest(cache=False)._cache is None
    shared: dict = {}
    assert Attest(cache=shared)._cache is shared


def test_llm_context_activates_the_instance_store():
    from attest import Attest

    judge = Attest(key="sk-test", cache=True)
    assert response_cache_module.response_cache.get() is None
    with judge._llm_context(required=True):
        assert response_cache_module.response_cache.get() is judge._cache
    assert response_cache_module.response_cache.get() is None


def test_llm_context_without_cache_leaves_store_unset():
    from attest import Attest

    judge = Attest(key="sk-test")
    with judge._llm_context(required=True):
        assert response_cache_module.response_cache.get() is None
