"""The few GitHub REST calls the Action makes, over the standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, cast

from pydantic import BaseModel, Field

from .payload import Json, as_obj, items, obj, optional_text, text

API_VERSION = "2022-11-28"
PAGE_SIZE = 100
MAX_FILES = 3000
"""GitHub's own cap on the files it lists for a pull request."""
TIMEOUT_SECONDS = 30


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API error {status}: {message}")
        self.status = status


class PullFile(BaseModel):
    path: str
    patch: str | None = None
    """None when GitHub sends no diff: a binary file, or one too large to show."""


class PullRequestData(BaseModel):
    number: int
    title: str = ""
    body: str = ""
    base_sha: str
    head_sha: str
    files: list[PullFile] = Field(default_factory=list[PullFile])
    commit_messages: list[str] = Field(default_factory=list[str])
    html_url: str = ""


class GitHub:
    """A GitHub REST client for one repository."""

    def __init__(self, token: str, repository: str, api_url: str = "https://api.github.com"):
        if not token:
            raise ValueError("No GitHub token: set the `github-token` input.")
        self._token = token
        self.repository = repository
        self._api = api_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        accept: str = "application/vnd.github+json",
    ) -> object:
        """Send one request; return parsed JSON, raw text for raw media types, or None on 404."""
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self._api}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": accept,
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "attest-github-action",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and method == "GET":
                return None
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise GitHubError(exc.code, _message(detail) or exc.reason) from exc
        if "raw" in accept:
            return raw
        return json.loads(raw) if raw else None

    def pull_request(self, number: int) -> PullRequestData:
        repo = self.repository
        pr = as_obj(self.request("GET", f"/repos/{repo}/pulls/{number}"))
        if not pr:
            raise GitHubError(404, f"pull request #{number} not found in {repo}")
        files = [
            PullFile(path=text(item, "filename"), patch=optional_text(item, "patch"))
            for item in self._pages(f"/repos/{repo}/pulls/{number}/files", MAX_FILES)
        ]
        commits = [
            text(obj(item, "commit"), "message")
            for item in self._pages(f"/repos/{repo}/pulls/{number}/commits", 250)
        ]
        base_sha, head_sha = text(obj(pr, "base"), "sha"), text(obj(pr, "head"), "sha")
        if not base_sha or not head_sha:
            raise GitHubError(500, f"pull request #{number} has no base or head commit")
        return PullRequestData(
            number=number,
            title=text(pr, "title"),
            body=text(pr, "body"),
            base_sha=base_sha,
            head_sha=head_sha,
            files=files,
            commit_messages=commits,
            html_url=text(pr, "html_url"),
        )

    def file_at(self, path: str, ref: str) -> str | None:
        """A file's text at `ref`, or None when it doesn't exist there."""
        quoted = urllib.parse.quote(path)
        ref_q = urllib.parse.quote(ref, safe="")
        found = self.request(
            "GET",
            f"/repos/{self.repository}/contents/{quoted}?ref={ref_q}",
            accept="application/vnd.github.raw+json",
        )
        return found if isinstance(found, str) else None

    def post_review(self, number: int, commit_id: str, body: str) -> str:
        """Post a comment-only review; return its URL."""
        review = self.request(
            "POST",
            f"/repos/{self.repository}/pulls/{number}/reviews",
            {"commit_id": commit_id, "body": body, "event": "COMMENT"},
        )
        return text(as_obj(review), "html_url")

    def post_comment(self, number: int, body: str) -> str:
        comment = self.request(
            "POST", f"/repos/{self.repository}/issues/{number}/comments", {"body": body}
        )
        return text(as_obj(comment), "html_url")

    def react(self, comment_id: int, content: str = "eyes") -> None:
        self.request(
            "POST",
            f"/repos/{self.repository}/issues/comments/{comment_id}/reactions",
            {"content": content},
        )

    def _pages(self, path: str, limit: int) -> list[Json]:
        found: list[Json] = []
        page = 1
        while len(found) < limit:
            raw = self.request("GET", f"{path}?per_page={PAGE_SIZE}&page={page}")
            found.extend(items(raw))
            if not isinstance(raw, list) or len(cast(list[object], raw)) < PAGE_SIZE:
                break
            page += 1
        return found[:limit]


def _message(detail: str) -> str:
    try:
        parsed: object = json.loads(detail)
    except ValueError:
        return detail.strip()
    return text(as_obj(parsed), "message") or detail.strip()
