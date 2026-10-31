"""CLI for attest. Every command (run, tools, injection, role, review, demo, stats, models,
schema) prints JSON."""

from __future__ import annotations

from .app import app

__all__ = ["app"]
