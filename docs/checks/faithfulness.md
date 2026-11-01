---
title: "Faithfulness: verify agent claims against tool outputs"
description: "The faithfulness check splits an agent's answer into claims and verifies each one against the real tool outputs to catch hallucinations."
---

# Faithfulness

**Question:** is every claim in the final answer backed by what the tools returned?

```bash
attest run run.json --checks faithfulness
```

```python
report = grader.evaluate(run, checks=("faithfulness",))
result = report.by("faithfulness")
```

## How it grades

1. The final answer is split into atomic, checkable claims. Hedges, opinions and generic advice
   are dropped.
2. Claims are checked against the run's tool outputs and artifacts in batches of 15, with one
   model call per batch. At most 40 claims are checked (`max_claims=` on `evaluate()`,
   `--max-claims` on `attest run` and `attest review`). Each claim past the cap is reported
   `unverifiable` with `checked` false, so a long answer goes to `review` instead of passing on
   its first 40 claims, and `attest review` drops a code review output with more claims than the
   cap.
3. Each claim gets `supported`, `unsupported` or `unverifiable`, a reason, and the deciding quote.
   When the quote comes from exactly one tool output or artifact, the finding's
   `metadata["location"]` says which, such as `steps[2].tool_call.artifacts[0]`.

The score is `supported / (supported + unsupported)`. Unverifiable claims don't count against
the score, but they appear as warnings. The check passes only when nothing is unsupported.
`metadata` counts the claims checked against the evidence (`claims_checked`) and every claim
extracted from the answer (`claims_total`), including any past the 40-claim limit.

**Inconclusive is not a pass.** When the answer has claims but none of them can be checked
(for example, the run recorded no relevant evidence), there's no score and the report's verdict
is `review`, not `pass`. Change it with
`VerdictPolicy(on_inconclusive_faithfulness=...)`. An answer that makes no claims at all
passes.

**Minimum coverage.** A run where only a few claims could be checked still passes by default.
To require more, set a minimum share of claims checked; below it, the run goes to review:

```python
Attest(verdict_policy=VerdictPolicy(min_claim_coverage=0.8))   # at least 80% of claims checked
```

Coverage is kept separate from the score: 1 claim checked out of 40 can still score 1.0. The
report gives it directly as `report.claim_coverage` (0 to 1, or `null` when faithfulness didn't
run or the answer made no claims).

**A failed call is not a pass either.** If claim extraction or a verification call fails, or a
verifier returns no verdict for a claim, the claims it covered are `unverifiable` with
`metadata["checked"]` set to `false` and the error in `reason`. Each one is `review` (the same
`on_inconclusive_faithfulness` setting), even when other claims were supported.
`metadata["claims_unchecked"]` counts them.

## Files as evidence

Artifact text counts as evidence, so a claim answered from an attached document can be checked.
PDFs, images and other binary files are read only when you opt in:

```python
grader = Attest(extract_artifacts=True)                    # data_base64 artifacts
grader = Attest(extract_artifacts=True, allow_paths=True)  # path artifacts too
```

Extraction uses the same limits as the injection scan. A file that was cut short or couldn't be
read is shown to the grading model as incomplete. Without the opt-in, binary and path artifacts
are left out and listed in `metadata["artifacts_unread"]`; files read only in part are listed in
`metadata["artifacts_incomplete"]`. See [Evidence](../concepts.md#evidence-and-the-grading-model).

## Choosing the standard

Pass `answer_kind` when the answer isn't a plain factual report (see
[Answer kinds](../concepts.md#answer-kinds)):

```python
grader.evaluate(run, answer_kind="plan")   # a plan or recommendation
grader.evaluate(run, answer_kind="code")   # an AI code reviewer's output
grader.evaluate(run, answer_kind="auto")   # pick factual or code from the evidence
```

The CLI takes the same choice as `--kind`.

## Bring your own extractor or verifier

Both steps are plain functions you can replace:

- `extract(answer) -> list[str]` splits the answer into claims.
- `verify(claims, evidence) -> list[Finding]` checks the claims against the evidence text.

```python
def extract(answer: str) -> list[str]:
    return [s.strip() for s in answer.split(".") if s.strip()]

report = grader.evaluate(run, checks=("faithfulness",), extract=extract)
```

## Compared with a plain LLM judge

`attest demo` grades the same run twice: once with a plain "is this answer good?" LLM judge
that reads everything, and once with attest:

```bash
attest demo examples/trajectory.json
```

Each comparison's `outcome` says who caught what: `caught` means attest found a false claim the
LLM judge passed. The other outcomes are `both_caught`, `both_passed` and `judge_only`.
