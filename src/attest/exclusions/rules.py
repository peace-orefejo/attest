"""Exclusions: the user's gitignore-style list of files attest leaves out of the evidence."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, PrivateAttr

from ..utils.ignore_paths import split_path
from ..utils.ignore_rules import IgnoreRule, parse_rules, parts_ignored

MAX_PATTERNS = 1_000
MAX_PATH_CHARS = 4_096
MAX_PATH_DEPTH = 1_024
EXCLUDED_REASON = "excluded by the user's exclusion rules"


class ExclusionError(ValueError):
    """An exclusion list or pattern file attest can't use: unreadable, too large or too long."""


class Exclusions(BaseModel):
    """Gitignore-style patterns naming files whose contents must never become evidence.

    Patterns apply in order and the last one matching a path decides, so a later `!` pattern
    re-includes a file. `sources` names the pattern files they were read from. More than
    `MAX_PATTERNS` patterns (blank lines and comments aside) raise `ExclusionError`.

    Matching fails closed. A path is normalized first (`\\` is a separator, `//` and `.` are
    dropped, `..` is resolved), and an absolute path, or one that climbs out with `..`, is
    matched from every one of its segments, since attest can't know where the repository
    starts. A path is also excluded when its case-folded, NFC-normalized form (with trailing
    spaces and dots trimmed from each segment) matches the case-folded patterns, because
    macOS and Windows treat those as the same file. A path over `MAX_PATH_CHARS` characters
    or `MAX_PATH_DEPTH` segments is always excluded.
    """

    model_config = ConfigDict(frozen=True)

    patterns: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    _compiled: list[IgnoreRule] | None = PrivateAttr(default=None)
    _folded: list[IgnoreRule] | None = PrivateAttr(default=None)

    def __init__(self, **data: object) -> None:
        super().__init__(**data)
        self._rules()

    @property
    def active(self) -> bool:
        """True when at least one pattern is set."""
        return bool(self._rules())

    def excludes(self, path: str, *, directory: bool = False) -> bool:
        """True when `path` (a directory, with `directory=True`) is excluded."""
        rules = self._rules()
        if not rules:
            return False
        if len(path) > MAX_PATH_CHARS:
            return True
        split = split_path(path)
        if len(split.parts) > MAX_PATH_DEPTH:
            return True
        floating = split.floating
        if parts_ignored(split.parts, rules, is_dir=directory, floating=floating):
            return True
        folded = tuple(_fold_segment(part) for part in split.parts)
        if folded == split.parts and self._folded is rules:
            return False
        return parts_ignored(folded, self._folded or [], is_dir=directory, floating=floating)

    def excluded(self, paths: Iterable[str]) -> list[str]:
        """The excluded paths among `paths`, in order and without repeats."""
        return list(dict.fromkeys(path for path in paths if self.excludes(path)))

    def _rules(self) -> list[IgnoreRule]:
        if self._compiled is None:
            rules = parse_rules(self.patterns)
            if len(rules) > MAX_PATTERNS:
                raise ExclusionError(
                    f"Too many exclusion patterns: {len(rules)}; the limit is {MAX_PATTERNS}."
                )
            folded = [_fold(pattern) for pattern in self.patterns]
            self._compiled = rules
            self._folded = rules if folded == list(self.patterns) else parse_rules(folded)
        return self._compiled


def excluded_note(path: str) -> str:
    """The one-line note that stands in for an excluded file's contents."""
    return f"{path}: {EXCLUDED_REASON}"


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())


def _fold_segment(part: str) -> str:
    return _fold(part).rstrip(" .") or part
