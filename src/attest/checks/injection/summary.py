from __future__ import annotations

from ...results import Finding
from ...utils.json_types import JsonObject

PAYLOAD_VERDICTS = frozenset({"suspicious", "possible_injection"})


def summarize(findings: list[Finding], deep: bool) -> str:
    if not findings:
        return (
            "No payloads detected and no unauthorized actions found."
            if deep
            else "No injection payloads detected in tool outputs."
        )
    payloads = [f for f in findings if f.verdict in PAYLOAD_VERDICTS]
    compromised = [f for f in findings if f.verdict == "compromised"]
    unscanned = [f for f in findings if f.verdict == "unscanned_content"]
    deep_failed = any(f.verdict == "unchecked" for f in findings)
    parts: list[str] = []
    if payloads:
        parts.append(f"{len(payloads)} untrusted segment(s) carry instruction-like content.")
    if compromised:
        parts.append(f"{len(compromised)} UNAUTHORIZED action(s) — likely a successful injection.")
    elif deep_failed:
        parts.append("The deep check failed, so the agent's actions were not checked.")
    elif payloads and deep:
        parts.append("But the agent did not take any unauthorized action.")
    elif payloads:
        parts.append("Run with deep=True to check whether the agent acted on them.")
    if unscanned:
        parts.append(f"{len(unscanned)} artifact(s) could not be scanned as text.")
    return " ".join(parts)


def result_metadata(
    findings: list[Finding],
    *,
    segments_scanned: int,
    artifacts_total: int,
    artifacts_scanned: int,
    deep_context_truncated: bool | None,
) -> JsonObject:
    unscanned_count = sum(f.verdict == "unscanned_content" for f in findings)
    return {
        "segments_scanned": segments_scanned,
        "artifacts_total": artifacts_total,
        "artifacts_scanned": artifacts_scanned,
        "artifacts_failed": artifacts_total - artifacts_scanned,
        "unscanned_count": unscanned_count,
        "coverage_complete": unscanned_count == 0,
        "patterns_attempted_before_timeout": _metadata_total(findings, "patterns_attempted"),
        "patterns_skipped_after_timeout": _metadata_total(findings, "patterns_skipped"),
        "deep_context_truncated": deep_context_truncated,
    }


def _metadata_total(findings: list[Finding], key: str) -> int:
    return sum(_as_int(f.metadata.get(key, 0)) for f in findings)


def _as_int(value: object) -> int:
    if isinstance(value, int | float | str):
        return int(value)
    return 0
