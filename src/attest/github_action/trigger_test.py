"""Which GitHub events ask attest for a review."""

from pathlib import Path

import pytest

from attest.github_action.settings import Settings
from attest.github_action.trigger import Skip, Trigger, decide


def _settings(**overrides):
    base = {
        "token": "t",
        "repository": "o/r",
        "event_name": "pull_request",
        "event_path": Path("event.json"),
        "reviewer": "attest-bot",
    }
    return Settings(**{**base, **overrides})


def _pr_event(action, **extra):
    pr = {"number": 7, "state": "open", "draft": False, **extra.pop("pr", {})}
    return {"action": action, "pull_request": pr, **extra}


def _comment_event(body, association="MEMBER", **extra):
    return {
        "action": extra.pop("action", "created"),
        "issue": {"number": 7, "state": "open", "pull_request": {"url": "x"}},
        "comment": {
            "id": 99,
            "body": body,
            "author_association": association,
            "user": {"login": "pat", "type": extra.pop("user_type", "User")},
        },
    }


def test_requesting_the_bot_as_reviewer_asks_for_a_review():
    event = _pr_event("review_requested", requested_reviewer={"login": "Attest-Bot"})
    assert decide("pull_request", event, _settings()) == Trigger(number=7, reason="requested")


@pytest.mark.parametrize(
    ("event", "settings", "why"),
    [
        (
            _pr_event("review_requested", requested_reviewer={"login": "alice"}),
            _settings(),
            "alice",
        ),
        (_pr_event("review_requested", requested_team={"slug": "core"}), _settings(), "team"),
        (
            _pr_event("review_requested", requested_reviewer={"login": "attest-bot"}),
            _settings(reviewer=""),
            "reviewer` input",
        ),
    ],
)
def test_other_review_requests_are_skipped(event, settings, why):
    outcome = decide("pull_request", event, settings)
    assert isinstance(outcome, Skip)
    assert why in outcome.why


def test_the_label_asks_for_a_review_and_other_labels_dont():
    settings = _settings()
    assert decide("pull_request", _pr_event("labeled", label={"name": "Attest"}), settings) == (
        Trigger(number=7, reason="label")
    )
    assert isinstance(
        decide("pull_request", _pr_event("labeled", label={"name": "bug"}), settings), Skip
    )


@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened", "ready_for_review"])
def test_updates_review_automatically_but_not_drafts(action):
    assert decide("pull_request_target", _pr_event(action), _settings()) == Trigger(
        number=7, reason="auto"
    )
    assert isinstance(
        decide("pull_request", _pr_event(action, pr={"draft": True}), _settings()), Skip
    )


def test_closed_pull_requests_and_other_actions_are_skipped():
    assert isinstance(
        decide("pull_request", _pr_event("opened", pr={"state": "closed"}), _settings()), Skip
    )
    assert isinstance(decide("pull_request", _pr_event("edited"), _settings()), Skip)
    assert isinstance(decide("push", {}, _settings()), Skip)
    assert isinstance(decide("pull_request", {"action": "opened"}, _settings()), Skip)


@pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR"])
def test_the_command_from_a_trusted_person_asks_for_a_review(association):
    event = _comment_event("/attest review please", association)
    assert decide("issue_comment", event, _settings()) == Trigger(
        number=7, reason="command", comment_id=99
    )


@pytest.mark.parametrize(
    ("event", "why"),
    [
        (_comment_event("/attest review", "CONTRIBUTOR"), "owner, members"),
        (_comment_event("/attest review", "NONE"), "owner, members"),
        (_comment_event("/attest review", user_type="Bot"), "bot"),
        (_comment_event("/attest reviewing later"), "start with"),
        (_comment_event("please /attest review"), "start with"),
        (_comment_event("/attest review", action="edited"), "new comments"),
    ],
)
def test_other_comments_are_skipped(event, why):
    outcome = decide("issue_comment", event, _settings())
    assert isinstance(outcome, Skip)
    assert why in outcome.why


def test_a_comment_on_an_issue_is_skipped():
    event = _comment_event("/attest review")
    del event["issue"]["pull_request"]
    assert isinstance(decide("issue_comment", event, _settings()), Skip)


def test_a_custom_command_is_matched_case_insensitively():
    event = _comment_event("/Review-Bot")
    assert decide("issue_comment", event, _settings(command="/review-bot")).reason == "command"


def test_settings_read_the_action_environment(tmp_path):
    settings = Settings.from_env(
        {
            "ATTEST_GITHUB_TOKEN": " tok ",
            "ATTEST_API_KEY": "k",
            "ATTEST_REVIEWER": "@attest-bot",
            "ATTEST_GUIDELINES": "",
            "ATTEST_ATTESTIGNORE": "false",
            "GITHUB_REPOSITORY": "o/r",
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_EVENT_PATH": str(tmp_path / "e.json"),
            "GITHUB_OUTPUT": str(tmp_path / "out"),
        }
    )
    assert settings.token == "tok"
    assert settings.reviewer == "attest-bot"
    assert settings.guidelines == "REVIEW.md"
    assert settings.guidelines_set is False
    assert settings.attestignore is False
    assert settings.model is None
    assert settings.output_path == tmp_path / "out"
    assert settings.summary_path is None
