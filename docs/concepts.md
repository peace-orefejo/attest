# How it works

![How attest checks an answer](assets/diagrams/how-it-works.svg){ .diagram }

## Runs

A run (`Trajectory`) records one task from start to finish:

| Field | Meaning |
|---|---|
| `task` | What the user asked. |
| `system_prompt` | The agent's instructions. The role check uses it as the job description. |
| `allowed_tools` | Tools the agent may call. Calls outside this list fail the tool-use check. |
| `steps` | Each step has an optional `thought` and an optional `tool_call` with `name`, `arguments` and `output`. |
| `artifacts` | Files or images the agent received, such as a PDF or a screenshot. |
| `final_answer` | What the agent told the user. |

## Evidence

Tool outputs are the only evidence attest trusts. Each one goes to the judge in its own escaped
block, so a web page or file can't pass itself off as another tool's result. The agent's
`thought` text is never shown to the judge.

## Claims and verdicts

The faithfulness check splits the final answer into atomic claims, then judges each claim
against the evidence:

| Verdict | Meaning | Severity |
|---|---|---|
| `supported` | The evidence entails the claim. | PASS |
| `unsupported` | The evidence contradicts the claim. | FAIL |
| `unverifiable` | The evidence doesn't mention it either way. | WARN |

Each finding carries the claim (`subject`), a `reason`, and the exact span of evidence that
decided it (`evidence`).

## Answer kinds

What counts as "supported" depends on what the answer is. Pass `answer_kind` to pick the standard:

| Kind | Use for | Standard |
|---|---|---|
| `factual` | Reports of facts the tools returned. | The evidence must entail the claim. |
| `plan` | Plans and recommendations. | The claim must match the plan in the evidence. Nothing has to have run yet. |
| `code` | Outputs of an AI code reviewer. | The diff and source must support the claim, read with the language's semantics. See [Code review mode](code-review/index.md). |
| `auto` | Mixed workloads. | Picks `factual` or `code` from the shape of the evidence. |

## Reports

`Attest.evaluate` returns a `Report` with one result per check. It passes only when every check
passes, and `overall_score` is the mean of the checks that score. Each result records the
`prompt_version` it was graded with.

## Scores and error bars

A pass rate from 20 runs is noisy. attest reports rates with a Wilson 95% confidence interval:

```bash
attest stats 41 50
# 82% (95% CI 69%–90%, n=50)
```

```python
from attest import difference_is_real

difference_is_real(41, 50, 35, 50)   # False: the gap is within noise
```

## What attest doesn't do

attest is read-only. It never runs your tools, calls your agent, or needs credentials for
anything except the grading model. It judges what was recorded, so a run that leaves out a tool
output can't be checked against it.
