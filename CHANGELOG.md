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
- Opt-in real-LLM integration tests behind the `integration` marker and `ATTEST_INTEGRATION=1`.
- `Attest.review(pr, outputs)` and `attest.code_review.review(...)` check and gate every output of
  a code review in one call. The result, `ReviewResult`, has one `OutputDecision` per output
  (`text`, `keep`, `mode`, `score`, `reasons`, `notes`, `omissions`), plus the guidelines used,
  `kept`, `dropped` and `filter()`. Outputs without their own diffs use the pull request's.
- Team review rules: pass `guidelines="REVIEW.md"` (or several files, or markdown text) to
  `review()`. Each list item in the markdown is a rule. The rules are added to every output's
  evidence, so an issue that cites one can be graded, and a new `guidelines` check drops any output
  that breaks a rule (`breaks_guideline`). An output that only leaves out something a rule asks
  for is kept with a `misses_guideline` note. Each finding must quote the output exactly, and each
  break is confirmed by a second call that asks separately whether the output reports, approves or
  itself does what the rule forbids; reporting rule-breaking code is never a break.
  `follow_guidelines=False` turns the check off. Without guidelines, outputs are checked for
  faithfulness only, and attest's own reviewer follows a built-in general standard.
- attest can write the review itself: `Attest.write_review(pr, guidelines=...)`, or `review(pr)`
  with no outputs, produces issues, one summary per changed file and an overview, then checks them
  like any reviewer's output. It always follows the general standard as a baseline; team rules add
  to it and win where they conflict.
- `attest review FILE` reads `{"pr": ..., "outputs": [...]}` and prints one decision per output.
  Leave out `outputs` to have attest write the review. `--guidelines/-g PATH` (repeatable) passes
  review rules, `--no-follow` skips the rule check, and `--mode TYPE=MODE` overrides a gate mode.
- `attest.render(result)` and `attest.show(result)` turn any `Report`, `CheckResult`,
  `ReviewResult` or `GateDecision` into a structured view: a status line, a summary table, and
  aligned findings with reasons and evidence.
- `--json` on `stats`, `models` and `demo`, so every command can emit JSON.
- `answer_kind` accepts `"code"` and `"auto"`. `"auto"` picks the grading standard from the run
  and records the choice in the report metadata.
- Two new default injection detectors: hidden Unicode (bidi controls, zero-width and tag
  characters) and encoded payloads (base64 and hex that decode to instructions).
### Changed
- Faithfulness and tool-choice prompts put the shared evidence before the per-call text;
  `PROMPT_VERSION` is now `2026.10.29`.
- `vote` stops sampling once a verdict holds a strict majority (2 of 3 agreeing skips the third
  call), cutting self-consistency spend by up to a third with identical verdicts.
- The LangGraph adapter discriminates messages by their stable `BaseMessage.type` role instead of
  the class name, so a LangChain class rename no longer breaks it silently.
- Split the monolithic `extraction` module into an `extraction/` package
  (`limits`, `pdf`, `image`, `markup`, `tabular`, `core`) behind an unchanged public API.
- Codebase reorganized for readability behind an unchanged public API: prompts live in a shared
  `prompts/` package, LLM plumbing in `llm/`, shared helpers in `utils/`, and `policy`,
  `checks.injection` and `cli` are now packages of small modules.
- `ExtractionLimits`, `ExtractionOutcome`, `RegexPattern`, `Budget` and `Usage` are Pydantic models.
  Invalid values raise pydantic `ValidationError` (a `ValueError`).
- `Severity` is a `StrEnum`, so `str(Severity.PASS)` is `"pass"`.
- `Trajectory.tool_calls()` returns `IndexedToolCall(step, call)` named tuples; unpacking still works.
- Tests live next to their modules as `<module>_test.py`; ruff and strict pyright are configured.
- **Breaking:** `Report.overall_score` is `None` when no check produced a score, instead of 1.0.
- **Breaking:** `Trajectory.evidence()` wraps each tool call in a
  `<tool_output index=... name=... arguments=...>` block and escapes any such tag inside an output.
  Before, blocks were plain `[i] name(args) -> output` lines, so a tool output (a web page, a file,
  a diff) could fake another tool's result. Every model call is told how the blocks work.
  `PROMPT_VERSION` is now `2026.10.30`.
- Every command's terminal output now uses the same structured layout.
- `GateDecision` splits its findings: `reasons` are what dropped the output, and `notes` are
  findings shown alongside it that didn't, such as a suspicious hit or a compromised finding
  that affected a different output.
- A payload or suspicious hit in the pull request's title, description or commit messages now
  applies to every output. Before, no output matched its location, so it never dropped or noted
  anything.
- `review()` raises `ValueError` for a `diff_summary` with no diffs of its own when the pull
  request changes several files, since a summary describes one file.
- `ReviewResult.warnings` flags a pull request that changes the file its review rules were
  loaded from.
- `attest run`'s `mean_overall_score` leaves out reports with no overall score.
- `python -m attest.cli` works again after the CLI became a package.
- The code injection summary lists only the verdicts found, e.g. "3 hits: 1 payload, 2 suspicious."
- The `code` answer kind's verifier reads a `read_guidelines` evidence step as the team's rules:
  authoritative about what the team requires, never about what the code does.
- The claim extractor keeps an answer's bottom line as its own claim and receives the task as
  context, so a conclusion can't be reworded to fit the agent's own justification.
- Anthropic grading now uses native structured outputs (`messages.parse`) instead of instructor's
  forced tool call, so Claude 5.5-generation models such as `claude-sonnet-5-5` work.
- Sampling parameters are sent only to Anthropic models that accept them (Claude 4.6 and older);
  Claude Opus 4.7+ and the Claude 5 family run without `temperature`.
- Dependency bounds: `anthropic>=0.77,<2` and `instructor>=1.15.3,<2`.
- Added `claude-opus-5-5`, `claude-sonnet-5-5`, and `claude-haiku-5-5` to the curated Anthropic
  model list.
### Fixed
- `attest demo` no longer crashes when the grounding score is unavailable.
- Hard provider errors (auth, billing, bad request) are no longer retried as "empty responses":
  `call` raises the provider's own error after one attempt instead of three retries ending in a
  misleading "no parseable content" message. Empty candidates and unparseable output still retry.
- An answer whose claims were all unverifiable scored 100% ("0/0 grounded"). It now has no score
  and says none of its claims could be checked.
- Fresh installs that resolve `anthropic` 1.x and `instructor` 1.17 no longer fail every LLM call
  with `Messages.create() got an unexpected keyword argument 'temperature'`.
- A `.env` file in the working directory (or a parent) is now read by both the library and the
  CLI, but only for provider API keys that aren't already set. Other variables in it, such as a
  base URL that would redirect your key, are ignored.
- Terminal output shows control and bidi characters from tool outputs as visible escapes, so
  untrusted text can't clear the screen, hide lines, change colors or write to the clipboard.
- Duplicate keys in policy YAML are caught after YAML resolves them, so `true:` and `True:` no
  longer overwrite each other silently.
- Diff parsing keeps every line inside a hunk as content, so an added line shaped like a file
  header can't start a fake file and hide later lines from the injection scan.
- A `@generated` marker or a very long line added by the pull request no longer hides that file
  from the grader and the reviewer.
- Code injection scanning: a quoted "example" no longer discounts a high-confidence payload
  outside test and doc files; hitting a match or decode cap marks coverage incomplete; and the
  shell, Ruby, PHP, Java and Rust lexers recognise comment and string forms they used to miss.
- Scans that could take quadratic time on crafted input (hex runs, Python docstrings, unclosed
  HTML comments in review rules) are now linear.

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
