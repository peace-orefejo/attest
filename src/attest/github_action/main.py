"""Run one review: decide from the event, fetch the pull request, review it, post the result."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable

from ..api import Attest
from ..code_review import PullRequest, ReviewGuidelines
from ..code_review.guidelines import parse_guidelines
from ..llm.reasoning import parse_reasoning
from .comment import failure_body, review_body
from .github import GitHub, PullRequestData
from .payload import Json, as_obj, obj, text
from .settings import Settings
from .trigger import Skip, Trigger, decide


def main(settings: Settings | None = None, github: GitHub | None = None) -> int:
    """Review the pull request the event names, if it asks for one. Returns the exit code."""
    settings = settings or Settings.from_env()
    event = _load_event(settings)
    outcome = decide(settings.event_name, event, settings)
    if isinstance(outcome, Skip):
        _log(f"Skipping: {outcome.why}")
        _outputs(settings, reviewed="false")
        return 0
    github = github or GitHub(settings.token, settings.repository, settings.api_url)
    try:
        return _review(settings, event, outcome, github)
    except Exception as exc:  # report every failure the same way; the job decides if it fails
        return _fail(settings, outcome, github, f"{type(exc).__name__}: {exc}")


def _review(settings: Settings, event: Json, trigger: Trigger, github: GitHub) -> int:
    if not settings.api_key:
        return _fail(settings, trigger, github, _missing_key(settings, event))
    if trigger.comment_id is not None:
        _best_effort(lambda: github.react(trigger.comment_id or 0))
    data = github.pull_request(trigger.number)
    pr = _pull_request(data)
    undiffed = [f.path for f in data.files if f.patch is None]
    if not pr.diffs:
        _log("Skipping: GitHub sent no diff for any file in this pull request.")
        _outputs(settings, reviewed="false")
        return 0
    rules = _rules(settings, github, data.base_sha)
    exclude = _exclusions(settings, github, data.base_sha)
    _log(f"Reviewing #{data.number} ({trigger.reason}): {len(pr.diffs)} file(s) with a diff.")
    result = Attest(
        settings.api_key,
        provider=settings.provider,
        model=settings.model,
        exclude=exclude,
        reasoning=parse_reasoning(settings.reasoning),
    ).review(pr, None, guidelines=rules)
    if result.writer_failure is not None:
        return _fail(settings, trigger, github, result.writer_failure)
    body = review_body(
        result,
        head_sha=data.head_sha,
        undiffed=undiffed,
        rules=settings.guidelines if rules is not None else None,
    )
    url = github.post_review(data.number, data.head_sha, body)
    _summary(settings, body)
    kept = len(result.kept)
    _outputs(
        settings,
        reviewed="true",
        kept=str(kept),
        dropped=str(len(result.decisions) - kept),
        review_url=url,
    )
    _log(f"Posted the review: {url or '(no URL returned)'}")
    return 0


def _pull_request(data: PullRequestData) -> PullRequest:
    diffs = {
        f.path: f"--- a/{f.path}\n+++ b/{f.path}\n{f.patch}\n"
        for f in data.files
        if f.patch is not None
    }
    return PullRequest(
        diffs=diffs,
        changed_files=[f.path for f in data.files],
        title=data.title,
        description=data.body,
        commit_messages=data.commit_messages,
    )


def _rules(settings: Settings, github: GitHub, base_sha: str) -> ReviewGuidelines | None:
    """The review rules from the base branch, so the pull request can't rewrite them."""
    text = github.file_at(settings.guidelines, base_sha)
    if text is None:
        if settings.guidelines_set:
            raise ValueError(
                f"The rules file {settings.guidelines!r} isn't on the base branch. Add it "
                "there, or leave the `guidelines` input unset to use attest's general standard."
            )
        return None
    return parse_guidelines(text, settings.guidelines)


def _exclusions(settings: Settings, github: GitHub, base_sha: str) -> list[str]:
    """`.attestignore` patterns from the base branch, so the pull request can't add or drop any."""
    if not settings.attestignore:
        return []
    text = github.file_at(".attestignore", base_sha)
    return text.splitlines() if text else []


def _missing_key(settings: Settings, event: Json) -> str:
    head = text(obj(obj(obj(event, "pull_request"), "head"), "repo"), "full_name")
    if settings.event_name == "pull_request" and head and head != settings.repository:
        return (
            "no model key. This pull request comes from a fork, and GitHub doesn't give "
            "workflows secrets for those on `pull_request`. Ask for a review with the comment "
            "command instead, which runs with your secrets."
        )
    return "no model key. Set the `api-key` input from a repository secret."


def _fail(settings: Settings, trigger: Trigger, github: GitHub, why: str) -> int:
    print(f"::error title=attest review::{_annotation(why)}", file=sys.stderr)
    if trigger.asked:
        _best_effort(lambda: github.post_comment(trigger.number, failure_body(why)))
    _outputs(settings, reviewed="false")
    return 1 if settings.fail_on_error else 0


def _load_event(settings: Settings) -> Json:
    try:
        with settings.event_path.open(encoding="utf-8") as handle:
            event: object = json.load(handle)
    except (OSError, ValueError):
        return {}
    return as_obj(event)


def _best_effort(call: Callable[[], object]) -> None:
    try:
        call()
    except Exception as exc:  # a reaction or a failure note must never break the run
        _log(f"(ignored) {type(exc).__name__}: {exc}")


def _summary(settings: Settings, body: str) -> None:
    if settings.summary_path is not None:
        with settings.summary_path.open("a", encoding="utf-8") as handle:
            handle.write(body + "\n")


def _outputs(settings: Settings, **values: str) -> None:
    if settings.output_path is None:
        return
    with settings.output_path.open("a", encoding="utf-8") as handle:
        for name, value in values.items():
            handle.write(f"{name.replace('_', '-')}={value}\n")


def _annotation(text: str) -> str:
    return " ".join(text.split()).replace("%", "%25")


def _log(message: str) -> None:
    print(message, flush=True)
