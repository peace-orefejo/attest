"""Turn the added lines of a pull request into tagged text segments."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...utils.diff import FileDiff, parse_unified_diff
from ..models import PullRequest
from .lexers import SegmentKind, Span, lexer_for

PR_FILE = "<pr>"


class Segment(BaseModel):
    """A run of one kind of text from an added diff line or the pull request's own prose."""

    model_config = ConfigDict(frozen=True)

    kind: SegmentKind
    text: str
    file: str
    line: int
    part: str = ""

    def __init__(self, kind: SegmentKind, text: str, file: str, line: int, part: str = "") -> None:
        super().__init__(kind=kind, text=text, file=file, line=line, part=part)

    def line_at(self, offset: int) -> int:
        return self.line + self.text.count("\n", 0, max(0, offset))

    @property
    def subject(self) -> str:
        return f"{self.file} {self.part}" if self.part else f"{self.file}:{self.line}"


class _NewSideLine(BaseModel):
    number: int
    text: str
    added: bool


def file_diffs(pr: PullRequest) -> list[FileDiff]:
    """Parse every diff in the pull request, naming single-file diffs by their key."""
    parsed: list[FileDiff] = []
    for path, text in pr.diffs.items():
        files = parse_unified_diff(text, path=path)
        if len(files) == 1:
            files[0].path = path
        parsed.extend(files)
    return parsed


def build_segments(pr: PullRequest) -> list[Segment]:
    """All segments for a pull request: added diff lines first, then PR prose."""
    segments: list[Segment] = []
    for file_diff in file_diffs(pr):
        segments.extend(diff_segments(file_diff))
    return segments + pr_segments(pr)


def diff_segments(file_diff: FileDiff) -> list[Segment]:
    """Lex each hunk's new side with context, keeping only text on added lines."""
    lex = lexer_for(file_diff.path)
    segments: list[Segment] = []
    for run in _new_side_runs(file_diff):
        added = {line.number for line in run if line.added}
        for span in lex([(line.number, line.text) for line in run]):
            segments.extend(_restrict(span, added, file_diff.path))
    return segments


def pr_segments(pr: PullRequest) -> list[Segment]:
    """Prose segments for the pull request title, description and commit messages."""
    parts = [("title", pr.title), ("description", pr.description)]
    parts += [(f"commit {index + 1}", message) for index, message in enumerate(pr.commit_messages)]
    return [Segment("prose", text, PR_FILE, 1, part) for part, text in parts if text.strip()]


def _new_side_runs(file_diff: FileDiff) -> list[list[_NewSideLine]]:
    runs: list[list[_NewSideLine]] = []
    for hunk in file_diff.hunks:
        run = [
            _NewSideLine(number=line.new_no, text=line.text, added=line.kind == "+")
            for line in hunk.lines
            if line.kind != "-" and line.new_no is not None
        ]
        if any(line.added for line in run):
            runs.append(run)
    return runs


def _restrict(span: Span, added: set[int], file: str) -> list[Segment]:
    segments: list[Segment] = []
    group: list[str] = []
    group_start = 0
    for offset, text in enumerate(span.text.split("\n")):
        line = span.line + offset
        if line in added:
            if not group:
                group_start = line
            group.append(text)
            continue
        if group:
            segments.append(Segment(span.kind, "\n".join(group), file, group_start))
            group = []
    if group:
        segments.append(Segment(span.kind, "\n".join(group), file, group_start))
    return [segment for segment in segments if segment.text.strip()]
