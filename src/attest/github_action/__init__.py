"""The attest GitHub Action: review a pull request when asked, and post what holds up.

Run by `action.yml` at the repository root as `python -m attest.github_action`. It never checks
out or runs the pull request's code: it reads the diff through the GitHub API, and reads review
rules and `.attestignore` from the base branch, so a pull request can't change the rules it is
reviewed by.
"""

from __future__ import annotations

from .main import main
from .settings import Settings
from .trigger import Trigger, decide

__all__ = ["Settings", "Trigger", "decide", "main"]
