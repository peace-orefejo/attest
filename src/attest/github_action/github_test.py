"""The GitHub REST client: headers, 404s, errors and raw files — no network."""

import io
import json
import urllib.error

import pytest

from attest.github_action import github as gh
from attest.github_action.github import GitHub, GitHubError


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def sent(monkeypatch):
    requests = []
    replies = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _Response(reply.encode())

    monkeypatch.setattr(gh.urllib.request, "urlopen", fake_urlopen)
    return requests, replies


def _http_error(code, body):
    return urllib.error.HTTPError("u", code, "reason", {}, io.BytesIO(body.encode()))


def test_requests_carry_the_token_and_api_version(sent):
    requests, replies = sent
    replies.append(json.dumps({"html_url": "https://x/review"}))
    client = GitHub("tok", "o/r", "https://ghe.example/api/v3/")
    assert client.post_review(7, "abc", "body") == "https://x/review"
    (request,) = requests
    assert request.full_url == "https://ghe.example/api/v3/repos/o/r/pulls/7/reviews"
    assert request.get_header("Authorization") == "Bearer tok"
    assert request.get_header("X-github-api-version") == gh.API_VERSION
    assert json.loads(request.data) == {"commit_id": "abc", "body": "body", "event": "COMMENT"}


def test_a_missing_file_is_none_and_a_present_one_is_its_text(sent):
    requests, replies = sent
    replies += [_http_error(404, "{}"), "- rule one\n"]
    client = GitHub("tok", "o/r")
    assert client.file_at("REVIEW.md", "base") is None
    assert client.file_at("docs/my rules.md", "base") == "- rule one\n"
    assert requests[1].full_url.endswith("/contents/docs/my%20rules.md?ref=base")
    assert requests[1].get_header("Accept") == "application/vnd.github.raw+json"


def test_errors_carry_githubs_message(sent):
    _, replies = sent
    replies.append(_http_error(403, json.dumps({"message": "Resource not accessible"})))
    with pytest.raises(GitHubError, match="403: Resource not accessible") as caught:
        GitHub("tok", "o/r").post_comment(7, "hi")
    assert caught.value.status == 403


def test_a_token_is_required():
    with pytest.raises(ValueError, match="github-token"):
        GitHub("", "o/r")
