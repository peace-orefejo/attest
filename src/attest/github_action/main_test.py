"""A whole run of the Action against a fake GitHub, with attest's review faked — all offline."""

import json

import pytest

from attest import Attest, CheckResult
from attest.code_review import ReviewResult
from attest.code_review.review import OutputDecision
from attest.github_action import main as action_main
from attest.github_action.comment import MARKER, review_body
from attest.github_action.github import GitHub, GitHubError, PullFile, PullRequestData
from attest.github_action.settings import Settings

PATCH = "@@ -1 +1 @@\n-total = 0\n+total = 1"


class FakeGitHub(GitHub):
    def __init__(self, files=None, repo_files=None):
        super().__init__("t", "o/r")
        self.files = files or {"cart.py": PATCH}
        self.repo_files = repo_files or {}
        self.reviews = []
        self.comments = []
        self.reactions = []
        self.read = []
        self.line_comments = []
        self.refuse_lines = False

    def pull_request(self, number):
        return PullRequestData(
            number=number,
            title="Fix total",
            body="desc",
            base_sha="base123",
            head_sha="head4567890",
            files=[PullFile(path=p, patch=v) for p, v in self.files.items()],
            commit_messages=["fix"],
        )

    def file_at(self, path, ref):
        self.read.append((path, ref))
        return self.repo_files.get(path)

    def post_review(self, number, commit_id, body, comments=None):
        if comments and self.refuse_lines:
            raise GitHubError(422, "line must be part of the diff")
        self.reviews.append((number, commit_id, body))
        self.line_comments.append(comments or [])
        return "https://github.com/o/r/pull/7#review"

    def post_comment(self, number, body):
        self.comments.append((number, body))
        return ""

    def react(self, comment_id, content="eyes"):
        self.reactions.append(comment_id)


def _decision(index, output_type, text, keep, paths=("cart.py",)):
    return OutputDecision(
        index=index,
        output_type=output_type,
        text=text,
        keep=keep,
        mode="lenient",
        paths=list(paths),
    )


RESULT = ReviewResult(
    decisions=[
        _decision(0, "group_summary", "Sets the starting total to 1.", True, ()),
        _decision(1, "issue", "total now starts at 1, so every cart is off by one.", True),
        _decision(2, "issue", "BAD: invented bug", False),
        _decision(3, "diff_summary", "Changes the initial total.", True),
    ],
    injection=CheckResult(check="code_injection", passed=True),
    written=True,
)


@pytest.fixture
def reviews(monkeypatch):
    calls = []

    def fake_review(self, pr, outputs, **kwargs):
        calls.append({"attest": self, "pr": pr, "outputs": outputs, **kwargs})
        return RESULT

    monkeypatch.setattr(Attest, "review", fake_review)
    return calls


def _settings(tmp_path, event_name, event, **overrides):
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event))
    base = {
        "token": "t",
        "api_key": "sk-ant-test-key",
        "repository": "o/r",
        "event_name": event_name,
        "event_path": path,
        "reviewer": "attest-bot",
        "output_path": tmp_path / "out",
        "summary_path": tmp_path / "summary",
    }
    return Settings(**{**base, **overrides})


def _outputs(tmp_path):
    lines = (tmp_path / "out").read_text().splitlines()
    return dict(line.split("=", 1) for line in lines)


REQUESTED = {
    "action": "review_requested",
    "pull_request": {"number": 7, "state": "open"},
    "requested_reviewer": {"login": "attest-bot"},
}


def test_a_requested_review_posts_only_what_held_up(tmp_path, reviews):
    github = FakeGitHub(
        repo_files={"REVIEW.md": "- Flag money bugs.\n", ".attestignore": "*.lock\n"}
    )
    settings = _settings(tmp_path, "pull_request", REQUESTED)
    assert action_main(settings, github) == 0

    (call,) = reviews
    assert call["outputs"] is None
    assert call["pr"].diffs == {"cart.py": f"--- a/cart.py\n+++ b/cart.py\n{PATCH}\n"}
    assert call["pr"].title == "Fix total"
    assert call["guidelines"].name == "REVIEW.md"
    assert call["attest"].exclusions.patterns == ("*.lock",)
    assert github.read == [("REVIEW.md", "base123"), (".attestignore", "base123")]

    ((number, commit, body),) = github.reviews
    assert (number, commit) == (7, "head4567890")
    assert body.startswith(MARKER)
    assert "every cart is off by one" in body
    assert "invented bug" not in body
    assert "1 didn't hold up" in body
    assert _outputs(tmp_path) == {
        "reviewed": "true",
        "kept": "3",
        "dropped": "1",
        "review-url": "https://github.com/o/r/pull/7#review",
    }
    assert "### attest review" in (tmp_path / "summary").read_text()


def test_the_command_reacts_to_the_comment(tmp_path, reviews):
    event = {
        "action": "created",
        "issue": {"number": 7, "state": "open", "pull_request": {}},
        "comment": {"id": 5, "body": "/attest review", "author_association": "OWNER", "user": {}},
    }
    github = FakeGitHub()
    assert action_main(_settings(tmp_path, "issue_comment", event), github) == 0
    assert github.reactions == [5]
    assert len(github.reviews) == 1
    assert reviews[0]["guidelines"] is None


def test_skipped_events_do_nothing(tmp_path, reviews):
    event = {"action": "edited", "pull_request": {"number": 7}}
    github = FakeGitHub()
    assert action_main(_settings(tmp_path, "pull_request", event), github) == 0
    assert reviews == [] and github.reviews == [] and github.comments == []
    assert _outputs(tmp_path) == {"reviewed": "false"}


def test_a_missing_key_tells_the_person_who_asked(tmp_path, reviews):
    github = FakeGitHub()
    settings = _settings(tmp_path, "pull_request", REQUESTED, api_key="")
    assert action_main(settings, github) == 0
    assert reviews == []
    ((_, body),) = github.comments
    assert "no model key" in body


def test_a_fork_without_secrets_is_explained(tmp_path, reviews, capsys):
    event = {
        "action": "opened",
        "pull_request": {"number": 7, "state": "open", "head": {"repo": {"full_name": "x/r"}}},
    }
    github = FakeGitHub()
    settings = _settings(tmp_path, "pull_request", event, api_key="", fail_on_error=True)
    assert action_main(settings, github) == 1
    assert "fork" in capsys.readouterr().err
    assert github.comments == []  # nobody asked, so nothing is posted


def test_a_named_rules_file_missing_from_the_base_branch_fails(tmp_path, reviews):
    github = FakeGitHub()
    settings = _settings(
        tmp_path, "pull_request", REQUESTED, guidelines="docs/RULES.md", guidelines_set=True
    )
    assert action_main(settings, github) == 0
    assert reviews == []
    assert "docs/RULES.md" in github.comments[0][1]


def test_a_review_attest_couldnt_write_is_reported(tmp_path, monkeypatch):
    failed = ReviewResult(
        decisions=[],
        injection=CheckResult(check="code_injection", passed=True),
        writer_failure="the model call was cut off",
    )
    monkeypatch.setattr(Attest, "review", lambda self, pr, outputs, **kw: failed)
    github = FakeGitHub()
    assert action_main(_settings(tmp_path, "pull_request", REQUESTED), github) == 0
    assert github.reviews == []
    assert "cut off" in github.comments[0][1]


def test_a_pull_request_with_no_diffs_is_skipped(tmp_path, reviews):
    github = FakeGitHub(files={"logo.png": None})
    assert action_main(_settings(tmp_path, "pull_request", REQUESTED), github) == 0
    assert reviews == [] and github.reviews == []


def test_the_body_lists_files_without_a_diff_and_injection():
    flagged = RESULT.model_copy(
        update={"injection": CheckResult(check="code_injection", passed=False)}
    )
    body = review_body(flagged, head_sha="abcdef123", undiffed=["logo.png"], rules=None)
    assert "aimed at AI reviewers" in body
    assert "`logo.png`" in body
    assert "abcdef1" in body
    assert "`cart.py`: total now starts at 1" in body


def test_github_pages_through_files(monkeypatch):
    github = GitHub("t", "o/r")
    pages = {
        "/repos/o/r/pulls/7": {
            "title": "T",
            "body": None,
            "base": {"sha": "b"},
            "head": {"sha": "h"},
        },
        "/repos/o/r/pulls/7/files?per_page=100&page=1": [
            {"filename": f"f{i}.py", "patch": "@@"} for i in range(100)
        ],
        "/repos/o/r/pulls/7/files?per_page=100&page=2": [{"filename": "big.bin"}],
        "/repos/o/r/pulls/7/commits?per_page=100&page=1": [{"commit": {"message": "m"}}],
    }
    monkeypatch.setattr(github, "request", lambda method, path, body=None, **kw: pages[path])
    data = github.pull_request(7)
    assert len(data.files) == 101
    assert data.files[-1] == PullFile(path="big.bin", patch=None)
    assert data.body == "" and data.commit_messages == ["m"]


ON_LINE = ReviewResult(
    decisions=[
        OutputDecision(
            index=0,
            output_type="issue",
            text="total now starts at 1.",
            keep=True,
            mode="lenient",
            paths=["cart.py"],
            line=1,
            suggestion="total = 0",
        ),
        _decision(1, "issue", "A problem with no single line.", True),
    ],
    injection=CheckResult(check="code_injection", passed=True),
    written=True,
)


def test_issues_on_a_line_are_posted_on_it_with_a_suggestion(tmp_path, monkeypatch):
    monkeypatch.setattr(Attest, "review", lambda self, pr, outputs, **kw: ON_LINE)
    github = FakeGitHub()
    assert action_main(_settings(tmp_path, "pull_request", REQUESTED), github) == 0
    ((comment,),) = github.line_comments
    assert comment["path"] == "cart.py" and comment["line"] == 1 and comment["side"] == "RIGHT"
    assert "```suggestion\ntotal = 0\n```" in comment["body"]
    body = github.reviews[0][2]
    assert "Issues (2, 1 posted on their lines)" in body
    assert "no single line" in body and "starts at 1" not in body


def test_line_comments_github_refuses_go_in_the_body(tmp_path, monkeypatch):
    monkeypatch.setattr(Attest, "review", lambda self, pr, outputs, **kw: ON_LINE)
    github = FakeGitHub()
    github.refuse_lines = True
    assert action_main(_settings(tmp_path, "pull_request", REQUESTED), github) == 0
    assert github.line_comments == [[]]
    assert "`cart.py`: total now starts at 1." in github.reviews[0][2]
