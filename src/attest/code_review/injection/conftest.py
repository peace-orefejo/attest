from collections.abc import Callable, Sequence

import pytest

import attest.code_review.injection.confirm as confirm
import attest.code_review.injection.effect as effect

MakeDiff = Callable[..., str]


def _diff(
    path: str,
    added: Sequence[str],
    *,
    start: int = 1,
    before: Sequence[str] = (),
    after: Sequence[str] = (),
) -> str:
    body = [f" {line}" for line in before] + [f"+{line}" for line in added]
    body += [f" {line}" for line in after]
    old = len(before) + len(after)
    header = f"--- a/{path}\n+++ b/{path}\n@@ -{start},{old} +{start},{old + len(added)} @@\n"
    return header + "\n".join(body) + "\n"


@pytest.fixture
def make_diff() -> MakeDiff:
    return _diff


@pytest.fixture
def no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kwargs: object) -> None:
        raise AssertionError("the model must not be called")

    monkeypatch.setattr(confirm, "call", boom)
    monkeypatch.setattr(effect, "call", boom)
