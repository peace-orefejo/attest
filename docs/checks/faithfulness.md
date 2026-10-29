# Faithfulness

**Question:** is every claim in the final answer backed by what the tools returned?

```bash
attest run run.json --checks faithfulness
```

```python
report = judge.evaluate(run, checks=("faithfulness",))
result = report.by("faithfulness")
```

## How it grades

1. The final answer is split into atomic, checkable claims. Hedges, opinions and generic advice
   are dropped.
2. Claims are verified against `run.evidence()` in batches of 15, with one model call per batch.
   At most 40 claims are checked; the summary says when a long answer was cut short.
3. Each claim gets `supported`, `unsupported` or `unverifiable`, a reason, and the deciding quote.

The score is `supported / (supported + unsupported)`. Unverifiable claims don't count against
the score, but they appear as warnings. The check passes only when nothing is unsupported.

## Choosing the standard

Pass `answer_kind` when the answer isn't a plain factual report:

```python
judge.evaluate(run, answer_kind="plan")   # a plan or recommendation
judge.evaluate(run, answer_kind="code")   # an AI code reviewer's output
judge.evaluate(run, answer_kind="auto")   # pick factual or code from the evidence
```

The CLI takes the same choice as `--kind`.

## Bring your own extractor or verifier

`extract` and `verify` are plain functions, so you can swap either one:

```python
def extract(answer: str) -> list[str]:
    return [s.strip() for s in answer.split(".") if s.strip()]

report = judge.evaluate(run, checks=("faithfulness",), extract=extract)
```

## Compared with a plain LLM judge

`attest demo` runs a naive "is this answer good?" judge next to attest on the same run:

```bash
attest demo examples/trajectory.json
```

The naive judge reads the agent's reasoning. attest doesn't.
