# Changelog

All notable changes to `agent-attest` are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Machine-readable `--json` output for the `run`, `tools`, `injection`, and `role` commands.
- Provenance-aware `Artifact`, `TextSegment`, and `Detection` models for untrusted content.
- Extensible named regex detectors with categories, confidence, severity, bounded execution,
  match offsets, custom JSON pattern packs, and `--patterns-only`.
- Injection coverage metadata and a measured benign/malicious regression corpus.

### Changed
- API clients are created lazily, so deterministic tool-use and shallow injection checks run
  without an API key or provider client.
- Deep injection evaluation always checks novel payloads while receiving only a bounded,
  deduplicated, escaped, and explicitly delimited view of untrusted content.
- Low-confidence and educationally quoted matches are reported as `possible_injection` rather
  than being suppressed.

### Fixed
- Invalid, empty, or duplicate check selections and unsupported answer kinds now fail loudly
  instead of allowing an empty report to pass with a perfect score.
- Malformed trajectory files now report concise filename and JSONL line-number errors.
- User-uploaded artifact text can no longer enter the faithfulness evidence set.
- Catastrophic custom regular expressions are stopped by mandatory execution timeouts and
  incomplete scans report the attempted and skipped pattern counts.
- Attacker-provided deep-context delimiters are escaped so they cannot forge trusted prompt
  sections.

## [0.5.1] - 2026-06-25

Judge precision and reproducibility. These changes were driven by red-teaming a live agent
(a civic assistant) whose trajectories exposed two false-positive patterns in the checks.

### Fixed
- **`check_role_adherence` now sees the agent's tool calls and their outputs.** The judge
  previously received only the system prompt, task, and final answer, so any policy that
  conditions behaviour on tool use (e.g. "only state a phone number a tool returned") was
  judged blind and false-flagged compliant answers as `out_of_scope_complied`. The tool calls
  and outputs are now part of the judge's context.
- **`check_role_adherence` honours explicit policy carve-outs.** A policy with a headline
  domain plus named exceptions (safety, emergencies, first aid, helplines) no longer reads
  those exceptions as out of scope; honouring a behaviour the policy explicitly permits is
  `in_scope`.
- **`check_injection` deep mode no longer flags the agent for answering the user's own
  request.** Returning information a tool surfaced, or retrieving to fulfil the user's task,
  is authorized even when the same tool output also carried injected instructions. Only acting
  on a new, unrequested goal counts as a compromise.

### Added
- **Self-consistency voting (`attest._llm.vote`).** The verdict checks (`check_role_adherence`
  and `check_injection` deep) now sample the judge `samples` times (default 3) and take the
  majority verdict, which stabilises non-deterministic providers. Configurable per call via
  `samples=`.

### Changed
- **LLM calls are pinned to `temperature=0`** at the chokepoint for reproducibility.
- **`PROMPT_VERSION` bumped to `2026.06.25`** to reflect the revised role and injection prompts.

[0.5.1]: https://pypi.org/project/agent-attest/0.5.1/
