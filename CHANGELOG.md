# Changelog

All notable changes to `agent-attest` are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Opt-in response caching via `Attest(cache=True)` (or a shared dict), so re-evaluating an
  identical run reuses judge calls without collapsing `vote` self-consistency.
- Spend controls: `Attest(budget=Budget(max_calls=..., max_tokens=...))` fails closed with
  `BudgetExceeded` before a call that would pass the limit; every `Report.metadata["usage"]`
  and `Attest.usage` record calls, input/output tokens, and cache hits.
- Persistent response cache: `Attest(cache="path/")` stores verdicts on disk via `DiskCache`,
  namespaced by provider and model, so reruns across processes reuse them.
- Provider prompt caching: shared context (faithfulness evidence across claim batches, the task and
  tool list across tool-choice calls, the whole prompt across `vote` samples) now leads the
  prompt so Gemini and OpenAI implicit caches reuse it, with explicit `cache_control`
  breakpoints on Anthropic only when the prefix will be resent. `Usage` reports
  `cached_input_tokens` and `cache_write_tokens`.
- `attest run --max-calls/--max-tokens/--cache-dir`, with a usage line (or `usage` in `--json`);
  exits with code 2 when the budget stops a run.

### Changed
- Faithfulness and tool-choice prompts put the shared evidence before the per-call text;
  `PROMPT_VERSION` is now `2026.10.29`.
- `vote` stops sampling once a verdict holds a strict majority (2 of 3 agreeing skips the third
  call), cutting self-consistency spend by up to a third with identical verdicts.

### Fixed
- Hard provider errors (auth, billing, bad request) are no longer retried as "empty responses":
  `call` raises the provider's own error after one attempt instead of three retries ending in a
  misleading "no parseable content" message. Empty candidates and unparseable output still retry.

## [0.7.0] - 2026-08-13

### Added
- Instance-bound evaluation policies with YAML/JSON loading, deterministic text/tool rules,
  evidence-grounded and rubric rules, automatic enforcement, and stable policy identity hashes.
- Bounded extraction of JSON, CSV, XML, HTML, PDF, image OCR, image metadata, and QR content for
  prompt-injection scanning through the optional `files` dependency bundle.
- `--extract-files/--no-extract-files` and `--allow-paths` flags on the `injection` command, and
  matching `extract_files`, `allow_paths`, and `extraction_limits` options on `Attest.injection`.
- Total detection cap (`ExtractionLimits.max_detections`) that bounds custom detector output and
  terminates unbounded or infinite detector iterables, emitting `unscanned_content`.
- `examples/pdf_agent.py` end-to-end demo evaluating a PDF-reading agent for injection resistance,
  including "held" versus "compromised" trajectories.

### Changed
- Refreshed the provider model registry: Anthropic Claude 5 family, OpenAI GPT-5.6, and Gemini 3.x
  defaults and curated model lists.
- Disabled-extraction warnings are capped per artifact and summarized with an omitted count, so a
  large binary-artifact trajectory can no longer emit unbounded findings.

### Fixed
- `policy.py` no longer uses Python 3.12-only f-string syntax, restoring the declared 3.11 floor.
- Resolved static type errors across the injection, extraction, policy, API, and provider modules.

## [0.6.0] - 2026-07-30

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

[0.6.0]: https://github.com/adepeju4/attest/compare/v0.5.1...v0.6.0
[0.5.1]: https://pypi.org/project/agent-attest/0.5.1/
