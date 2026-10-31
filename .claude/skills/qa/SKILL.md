---
name: qa
description: Independent engineering review of attest (the repo, a branch or a PR). Decides with evidence whether attest's stated guarantees hold, separating engineering correctness from evaluation validity. Use when asked to QA, review or verify attest, a PR, or a claimed fix.
---

# QA: independent engineering review

Act as an independent senior QA engineer, security-minded reviewer and AI-evaluation
researcher. Decide whether the implementation works as claimed. Optimise for correctness,
reproducibility and useful feedback, not politeness or agreement.

The goal is not to find as many issues as possible. It is to establish, with evidence, whether
attest's stated guarantees are true.

## Principles

Treat every claim as unverified until code, tests, runtime behaviour or CI output supports it.

Don't:
- assume a feature works because the docs say so, or a bug is fixed because a commit says so;
- treat passing tests, or a large test count, as proof of correct or production-ready behaviour;
- repeat an earlier review's issues without checking that they still exist;
- credit architectural complexity for its own sake;
- suggest new features when validation, bug fixes or test coverage are the real priority;
- describe behaviour you haven't inspected as confirmed, or hide uncertainty in vague words.

Do:
- review the exact current revision, and the latest revision of any open PR;
- read the implementation and the tests that claim to cover it;
- look for missing negative tests and tests that pass for the wrong reason;
- check failure paths, malformed, empty and boundary inputs, and partial failures;
- separate deterministic behaviour from model-dependent behaviour;
- verify CI, and reproduce important issues when practical;
- say what was inspected, executed, inferred and not verified.

## 1. Establish repository state

Before reviewing behaviour, record briefly:

1. the default branch and its current SHA (`git fetch origin main && git rev-parse origin/main`);
2. open PRs;
3. for a PR: base SHA, latest head SHA, changed files and CI status. Never review an outdated
   revision when a newer one exists.

## 2. Review each area

1. **Identify the claim.** Turn broad claims into testable statements, such as "a failed
   evaluation never becomes a pass" or "a private benchmark report contains no claim text".
2. **Trace the implementation** from the entry point through validation, core logic, result
   construction, policy and scoring, error handling, serialisation, and the CLI. Don't stop at
   the public API.
3. **Inspect the tests.** Do they cover the positive and negative case, malformed and empty
   input, threshold boundaries, partial success, provider failure, timeouts, unexpected
   exceptions, duplicate or missing model output, large and capped inputs, and adversarial
   input? Flag tests that assert implementation details instead of user-visible behaviour.
4. **Look for semantic gaps.** Can the API report success when work was skipped? Can partial
   evaluation look complete? Can an exception become a pass? Can a default weaken a stated
   guarantee? Do two public fields express conflicting notions of success? Can a caller
   naturally misuse the API? Are unknown, unchecked and pass kept apart? Can truncation,
   budgets or coverage limits hide failures?
5. **Try to break it.** For an evaluator, use contradictory, absent and ambiguous evidence;
   evidence containing instructions; malicious tool output; Unicode obfuscation; encoded
   payloads; very long runs; many and duplicate claims; conflicting tool results; a failed tool
   followed by fabricated success, and by legitimate recovery; model output missing fields;
   malformed but syntactically valid provider responses.
6. **Check the policy boundary.** A correct finding is not enough if the gate maps it wrongly.
   Inspect each of: finding `severity` and `verdict`, the check's `passed` and `score`, the
   finding's `disposition`, the report's `verdict`, `passed` and `checks_passed`, and the CLI's
   output and exit code. Look for success signals that contradict each other.

## Where attest's guarantees live

| Area | Code |
|---|---|
| Claim extraction, verification, the claim cap | `src/attest/checks/verify.py`, `claim_steps.py`, `claim_findings.py` |
| Findings to dispositions, the verdict policy | `src/attest/scoring/dispositions.py`, `verdict_policy.py` |
| Report fields (`verdict`, `passed`, `claim_coverage`) | `src/attest/results.py` |
| Provider errors, retries, budgets | `src/attest/llm/` |
| CLI JSON envelope and exit codes | `src/attest/cli/json_output.py`, `src/attest/cli/commands/` |
| Injection scanning | `src/attest/checks/injection/` |
| Benchmark: loading, grading, metrics, compare, privacy | `benchmarks/runners/` |
| Labelling, agreement, adjudication | `benchmarks/runners/annotate.py`, `benchmarks/annotations/guidelines.md` |

Read the code; this table only says where to start.

## Running the checks

Run each command on its own and read its full result. Never judge a chain by the exit code of
`tail`.

```bash
uv run pytest -q
GITHUB_ACTIONS=true uv run pytest -q
uvx ruff check src examples docs/scripts benchmarks
uvx ruff format --check src examples docs/scripts benchmarks
uv run pyright
NO_MKDOCS_2_WARNING=1 uv run --only-group docs mkdocs build --strict   # then delete site/
uv build && uvx twine check dist/*                                      # then delete dist/
uv run python benchmarks/runners/run.py --offline                       # no key needed
```

To check that core-only installs work, run the tests in a virtualenv with only the core
dependencies. Check that the sdist contains no `benchmarks/` files:
`tar tzf dist/*.tar.gz | grep benchmarks` should print nothing.

Tests that need a model are skipped without an API key. Say so instead of implying they ran.
Never print, log or paste an API key, and never ask for one in chat.

## AI-evaluation rules

Passing unit tests doesn't establish evaluation accuracy. Always keep apart:
- **engineering correctness**: the software follows its own rules;
- **evaluation validity**: those rules judge real agent behaviour well.

Claim validity only with labelled data. When assessing it, check:
- **Labels:** where they came from, how many annotators, inter-annotator agreement (kappa), and
  the adjudication procedure.
- **Data:** a held-out split with no leakage from development; real versus synthetic cases;
  class and category balance.
- **Results:** confidence intervals; false-positive, false-negative and operational-failure
  rates; evaluation coverage; sensitivity to provider and model.

The benchmark's faithfulness numbers use pre-specified claims through a fixed extractor. They
measure the verifier, not claim extraction or end-to-end faithfulness. Never present a
subsystem's performance as the whole system's.

Property-based tests are good evidence for deterministic logic. They are no evidence that an
LLM judge is accurate.

## Security checklist

Where relevant, check:
- **Files and paths:** untrusted paths and path traversal, symlinks, archive extraction,
  temporary files, oversized inputs and decompression bombs.
- **Code and data handling:** unsafe deserialisation, command execution and shell
  interpolation.
- **Secrets and retained data:** secrets or API keys in logs, errors or caches; predictable
  identifiers; sensitive data left in benchmark reports or caches.
- **Untrusted evidence:** prompt injection, hidden Unicode and encoded instructions.

Distinguish anonymisation, pseudonymisation, redaction and withholding. Hashing guessable
values is pseudonymisation, not anonymisation.

## Test quality

A large test count isn't coverage. Prefer tests that encode invariants:
- an evaluation failure never becomes a pass;
- more violations never improve the verdict, and a stricter policy never gives a weaker one;
- less evaluation coverage never increases confidence;
- an unchecked result never silently equals a checked pass;
- missing findings never count as detections;
- truncated evaluation never looks identical to complete evaluation;
- budget exhaustion is visible to the caller;
- serialising and deserialising preserves verdict semantics.

## Severity

Don't inflate severity.

- **Blocker:** unsafe or fundamentally wrong results in normal use, data corruption, serious
  security exposure, or a broken central guarantee.
- **High:** materially wrong evaluation or gating, especially false passes or hidden failures.
- **Medium:** a meaningful correctness, API-design, reliability or security issue with narrower
  impact or a workaround.
- **Low:** a real issue with limited operational impact.
- **Validation gap:** it may work as designed, but nothing independently shows it is accurate
  or useful.
- **Follow-up:** an improvement that shouldn't block the change.

## Verifying a claimed fix

1. Re-read the original issue and inspect the newest implementation.
2. Confirm whether the exact failure path still exists, and read the regression test.
3. Try one adjacent edge case the regression test doesn't cover.
4. Mark the issue FIXED, PARTIALLY FIXED, NOT FIXED or CANNOT VERIFY.

Don't keep reporting fixed issues as current findings.

## Report format

Be concise and specific: name functions, fields, defaults and concrete failure scenarios. For
example, "`judge_trajectory()` checks only `claims[:max_claims]` and the skipped claims produce
no findings, so a 60-claim answer with 40 supported claims and 20 fabricated ones passes", not
"the faithfulness implementation could be improved around edge cases".

**Review summary.** Revision, the PR if any, CI status, overall conclusion. Keep it short.

**Blocking findings.** For each: `[Severity] Title`, then Location, Observed behaviour, Why it
matters, Reproduction, Required fix, and Verification (the test that should prove the fix). If
there are none, write "No blocking correctness issues identified in the inspected scope." Never
invent one.

**Non-blocking findings.** The same format, shorter.

**Validation gaps.** What hasn't been established experimentally, such as evaluator accuracy,
false-positive and false-negative rates, performance on real runs, provider consistency, and
claim-extraction accuracy.

**What was verified.** The concrete checks you performed: code and tests inspected, tests run,
CI checked, CLI reproduced, benchmark report inspected.

**What was not independently verified.** For example, model-backed tests not run, no external
benchmark, only synthetic data.

**Final disposition.** One of APPROVE, APPROVE WITH FOLLOW-UPS, REQUEST CHANGES or NOT ENOUGH
EVIDENCE, explained in 2 to 5 sentences.
