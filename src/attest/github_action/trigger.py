"""Decide from the GitHub event whether to review, and which pull request."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .payload import Json, integer, obj, text
from .settings import Settings

Reason = Literal["requested", "command", "label", "auto"]

PR_EVENTS = ("pull_request", "pull_request_target")
AUTO_ACTIONS = ("opened", "synchronize", "reopened", "ready_for_review")
TRUSTED_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")


class Trigger(BaseModel):
    """Review this pull request, for this reason."""

    number: int
    reason: Reason
    comment_id: int | None = None
    """The `/attest review` comment, to react to."""

    @property
    def asked(self) -> bool:
        """True when a person asked for this review, so they should hear back even on failure."""
        return self.reason != "auto"


class Skip(BaseModel):
    """Don't review; `why` goes in the log."""

    why: str


def decide(event_name: str, event: Json, settings: Settings) -> Trigger | Skip:
    """Whether this event asks for a review.

    - Requested as a reviewer: the requested login is `settings.reviewer`.
    - A comment on a pull request that starts with `settings.command`, from the repository's
      owner, a member or a collaborator.
    - The `settings.label` label added.
    - Opened, updated, reopened or marked ready (draft pull requests are skipped).
    """
    if event_name == "issue_comment":
        return _comment(event, settings)
    if event_name not in PR_EVENTS:
        return Skip(why=f"attest doesn't review on `{event_name}` events.")
    action = text(event, "action")
    pr = obj(event, "pull_request")
    number = integer(pr, "number")
    if number is None:
        return Skip(why="The event has no pull request.")
    if text(pr, "state") == "closed":
        return Skip(why="The pull request is closed.")
    if action == "review_requested":
        requested = text(obj(event, "requested_reviewer"), "login")
        if not settings.reviewer:
            return Skip(why="A reviewer was requested, but the `reviewer` input isn't set.")
        if requested.lower() != settings.reviewer.lower():
            return Skip(why=f"The requested reviewer is {requested or 'a team'}, not attest.")
        return Trigger(number=number, reason="requested")
    if action == "labeled":
        name = text(obj(event, "label"), "name")
        if name.lower() != settings.label.lower():
            return Skip(why=f"The label added is {name!r}, not {settings.label!r}.")
        return Trigger(number=number, reason="label")
    if action in AUTO_ACTIONS:
        if pr.get("draft") is True:
            return Skip(why="The pull request is a draft.")
        return Trigger(number=number, reason="auto")
    return Skip(why=f"attest doesn't review on `{action}`.")


def _comment(event: Json, settings: Settings) -> Trigger | Skip:
    if text(event, "action") != "created":
        return Skip(why="Only new comments can ask for a review.")
    issue = obj(event, "issue")
    if "pull_request" not in issue or issue["pull_request"] is None:
        return Skip(why="The comment is on an issue, not a pull request.")
    if text(issue, "state") == "closed":
        return Skip(why="The pull request is closed.")
    comment = obj(event, "comment")
    body = text(comment, "body").strip()
    command = settings.command.strip()
    if not _starts_with_command(body, command):
        return Skip(why=f"The comment doesn't start with {command!r}.")
    if text(obj(comment, "user"), "type") == "Bot":
        return Skip(why="The comment is from a bot.")
    if text(comment, "author_association") not in TRUSTED_ASSOCIATIONS:
        return Skip(
            why="Only the repository's owner, members and collaborators can ask for a review."
        )
    number = integer(issue, "number")
    if number is None:
        return Skip(why="The event has no pull request number.")
    return Trigger(number=number, reason="command", comment_id=integer(comment, "id"))


def _starts_with_command(body: str, command: str) -> bool:
    if not body.lower().startswith(command.lower()):
        return False
    rest = body[len(command) :]
    return not rest or rest[0].isspace()
