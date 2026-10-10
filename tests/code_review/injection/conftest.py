import pytest


def _diff(path, added, *, start=1, before=(), after=()):
    body = [f" {line}" for line in before] + [f"+{line}" for line in added]
    body += [f" {line}" for line in after]
    old = len(before) + len(after)
    header = f"--- a/{path}\n+++ b/{path}\n@@ -{start},{old} +{start},{old + len(added)} @@\n"
    return header + "\n".join(body) + "\n"


@pytest.fixture
def make_diff():
    return _diff


@pytest.fixture
def no_model(monkeypatch):
    import attest.code_review.injection.confirm as confirm
    import attest.code_review.injection.effect as effect

    def boom(**kwargs):
        raise AssertionError("the model must not be called")

    monkeypatch.setattr(confirm, "call", boom)
    monkeypatch.setattr(effect, "call", boom)
