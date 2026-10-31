---
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
2. Claims are checked against the run's tool outputs in batches of 15, with one model call per batch.
   At most 40 claims are checked; the summary says when a long answer was cut short.
3. Each claim gets `supported`, `unsupported` or `unverifiable`, a reason, and the deciding quote.

The score is `supported / (supported + unsupported)`. Unverifiable claims don't count against
the score, but they appear as warnings. The check passes only when nothing is unsupported.

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
