---
description: "How attest grades AI agents: runs, evidence from tool outputs, atomic claims, verdicts, answer kinds and scores with confidence intervals."
---

# How it works

attest takes a **run**, a record of what an agent did, and treats its tool outputs as the only
evidence. Each **check** compares part of the run against that evidence and returns a
**result** made of **findings**. `evaluate()` collects the results into a **report**.

![How attest checks an answer](assets/diagrams/how-it-works.svg){ .diagram }

## Runs

A run records one task from start to finish. In Python it is a `Trajectory`; on the command
line it is one JSON object (a `.jsonl` file holds one per line).

| Field | Meaning |
|---|---|
| `task` | What the user asked. |
| `system_prompt` | The agent's instructions. The role check uses it as the job description. |
| `allowed_tools` | Tools the agent may call. Calls outside this list fail the tool-use check. |
| `tool_fallbacks` | Optional. For each tool, the tools that can stand in for it when it errors, such as `{"charge_card": ["charge_card_backup"]}`. |
| `steps` | Each step has an optional `thought` and an optional `tool_call` with `name`, `arguments`, `output` and an optional `is_error` that overrides attest's guess. |
| `artifacts` | Files or images the agent received, such as a PDF or a screenshot. |
| `final_answer` | What the agent told the user. |

## Evidence and the grading model

Tool outputs and artifacts are the only evidence attest trusts. Checks that need judgment, such
as faithfulness, ask a language model (the **grading model**) one narrow question: does this
evidence support this claim?

That is the difference from a plain "LLM judge", which reads the whole run and decides whether
the answer looks good. The grading model sees each tool output and each artifact in its own
escaped block and never sees the agent's `thought` text, so confident reasoning can't talk it
into a pass.

An artifact's block comes right after the output of the tool that returned it; artifacts on the
run itself come last. Artifacts with `source: "user_upload"` are not evidence. Artifact `text`
is always used. Binary (`data_base64`) and `path` artifacts are read only when you opt in with
`Attest(extract_artifacts=True)`, through the same size-limited extraction the injection scan
uses; `path` artifacts also need `allow_paths=True`. A file that was cut short or couldn't be
read is marked `complete="false"`, and the grading model is told not to count its missing parts
as support. Files left out are listed in the result's `metadata["artifacts_unread"]`.

## Results and findings

Every check returns a result with the same fields:

| Field | Meaning |
|---|---|
| `check` | The check's name: `faithfulness`, `tool_use`, `injection`, `role` or `policy`. |
| `passed` | Whether the check passed. |
| `score` | Between 0 and 1, or `null` for checks that don't score (role, injection). |
| `summary` | One line for people. |
| `findings` | One per claim, tool call or payload. |

Each finding has a `severity` of `pass`, `warn` or `fail`, and a `verdict` that depends on the
check, such as `unsupported` or `suspicious`. It names what it is about (`subject`), explains
itself (`reason`), and quotes the deciding tool output (`evidence`). `step` is the step index
when the finding is about one step.

## Claims and verdicts

The faithfulness check splits the final answer into atomic claims and checks each one:

| Verdict | Means | Severity |
|---|---|---|
| `supported` | The evidence backs the claim. | `pass` |
| `unsupported` | The evidence contradicts the claim. | `fail` |
| `unverifiable` | The evidence doesn't say either way. | `warn` |

## Answer kinds

What counts as "supported" depends on what the answer is. Pass `answer_kind=` to `evaluate()`,
or `--kind` to `attest run`:

| Kind | Use for | Standard |
|---|---|---|
| `factual` (default) | Reports of facts the tools returned. | The evidence must back the claim. |
| `plan` | Plans and recommendations. | The claim must match the plan in the evidence. Nothing has to have run yet. |
| `code` | Outputs of an AI code reviewer. | The diff and source must support the claim, read with the language's semantics. See [Code review mode](code-review/index.md). |
| `auto` | Mixed workloads. | Picks `factual` or `code` from the evidence. |

## Reports

`evaluate()` runs faithfulness and tool use by default; pass `checks=` for others. It returns a
`Report` with one result per check, plus a `policy` result when the `Attest` has a
[policy](checks/policies.md). `passed` is true when the report's `verdict` (below) is
`pass`; `checks_passed` is true when every check passed, even if something still needs review. Its
`overall_score` is the mean of the scores that aren't `null`, and `scores` gives each check's
score by name.

Checks say what happened. A `VerdictPolicy` decides what happens because of it: each finding
gets a `disposition` of `pass`, `review` or `block`, and the report's `verdict` is the strictest
one. A blocking finding can't be averaged away by good scores elsewhere. `blocking` lists the
findings that blocked, with their check, verdict and subject. attest only reports; your code
decides what to do with the verdict.

By default these block: an `unsupported` claim, a disallowed tool, a tool error the answer
reported as success, a `compromised` injection, an out-of-scope request the agent complied with,
and a failed `fail`-severity policy rule. These go to review: a tool error the agent ignored, an
unnecessary tool call, a `warn`-severity policy rule, and a faithfulness result where no claim
could be checked against the evidence. Injection warnings pass, and so do `unverifiable` claims
when at least one other claim was checked. Any other failed finding blocks.

```python
from attest import Attest, ToolUsePolicy, VerdictPolicy

judge = Attest(
    verdict_policy=VerdictPolicy(
        tool_use=ToolUsePolicy(on_unhandled_error="block"),
        on_injection_warning="review",
        min_score={"faithfulness": 0.9},  # below 0.9, passing claims go to review
    )
)
report = judge.evaluate(run)
if report.verdict == "block":
    raise SystemExit(f"blocked by {report.blocking}")
```

`ToolUsePolicy` also takes `on_disallowed_tool`, `on_claimed_success` and `on_unnecessary_call`.
`VerdictPolicy` also takes `on_inconclusive_faithfulness` (default `review`) and
`min_claim_coverage`, the lowest share of claims faithfulness must check before a run can pass
(off by default).

## Pass rates and confidence

A pass rate from 20 runs is noisy. `attest stats` turns a pass count into a rate with a Wilson
95% confidence interval:

```bash
attest stats 41 50 | jq '.data'
# {"rate": 0.82, "low": 0.69, "high": 0.90, "n": 50}   (values rounded here)
```

```python
from attest import difference_is_real

difference_is_real(41, 50, 35, 50)   # False: the gap is within noise
```

## What attest doesn't do

attest is read-only. It never runs your tools, calls your agent, or needs credentials for
anything except the grading model. It can only check what the run recorded, so a tool output
that is missing from the run can't be used as evidence. [Limitations](limitations.md) lists what
attest assumes and where its checks rely on heuristics.
