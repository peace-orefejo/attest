"""Exclusions: the user's gitignore-style list of files attest leaves out of the evidence."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, PrivateAttr

from ..utils.ignore_rules import IgnoreRule, is_ignored, parse_rules

MAX_PATTERNS = 1_000
EXCLUDED_REASON = "excluded by the user's exclusion rules"


class ExclusionError(ValueError):
    """An exclusion list or pattern file attest can't use: unreadable, too large or too long."""


class Exclusions(BaseModel):
    """Gitignore-style patterns naming files whose contents must never become evidence.

    Patterns apply in order and the last one matching a path decides, so a later `!` pattern
    re-includes a file. `sources` names the pattern files they were read from. More than
    `MAX_PATTERNS` patterns (blank lines and comments aside) raise `ExclusionError`.
    """

    model_config = ConfigDict(frozen=True)

    patterns: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    _compiled: list[IgnoreRule] | None = PrivateAttr(default=None)

    def __init__(self, **data: object) -> None:
        super().__init__(**data)
        self._rules()

    @property
    def active(self) -> bool:
        """True when at least one pattern is set."""
        return bool(self._rules())

    def excludes(self, path: str, *, directory: bool = False) -> bool:
        """True when `path` (a directory, with `directory=True`) is excluded."""
        return is_ignored(path, self._rules(), is_dir=directory)

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
            self._compiled = rules
        return self._compiled


ExclusionsInput = Exclusions | str | Sequence[str] | None
"""An `Exclusions`, one pattern, a list of patterns, or None for no exclusions."""


def as_exclusions(value: ExclusionsInput) -> Exclusions:
    """Turn any accepted exclusion input into `Exclusions`."""
    if value is None:
        return Exclusions()
    if isinstance(value, Exclusions):
        return value
    if isinstance(value, str):
        return Exclusions(patterns=(value,))
    return Exclusions(patterns=tuple(value))


def excluded_note(path: str) -> str:
    """The one-line note that stands in for an excluded file's contents."""
    return f"{path}: {EXCLUDED_REASON}"
