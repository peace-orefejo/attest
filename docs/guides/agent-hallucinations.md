---
title: "Detecting hallucinations in tool-using AI agents"
description: "How to detect hallucinations in AI agents that call tools: check each claim against the tool outputs, and catch failed actions reported as success."
---

# Detecting hallucinations in tool-using agents

A tool-using agent has the facts in front of it: the tools returned them. It can still
hallucinate. The useful question is not "does this answer sound right?" but "did the tools say
this?", and that question has an answer you can check.

## How agents hallucinate with the evidence in hand

| Kind | Example |
|---|---|
| **A wrong detail** | The tool returned 2,103,000; the answer says 2.4 million. |
| **A wrong conclusion from right data** | Both populations are quoted correctly, then the answer says the smaller city is larger. |
| **A claim from nowhere** | The answer adds an opening date no tool ever returned. |
| **An action that didn't happen** | The refund call failed with a timeout; the answer says "your refund has been processed". |

The first three are about the answer's facts. The fourth is about the agent's actions, and it is
often the most costly: the user is told something was done when it wasn't.

## Check each claim against the tool outputs

attest's [faithfulness check](../checks/faithfulness.md) splits the final answer into atomic
claims and checks each one against the run's tool outputs and artifacts:

| Verdict | Means | Default disposition |
|---|---|---|
| `supported` | The evidence backs the claim. | `pass` |
| `unsupported` | The evidence contradicts the claim. | `block` |
| `unverifiable` | The evidence doesn't say either way. | `pass` if other claims were checked, otherwise `review` |

The grading model sees each claim with the tool outputs, and never the agent's reasoning, so a
persuasive chain of thought can't argue a wrong claim into a pass. Each finding quotes the
deciding tool output in `evidence`.

```python
from attest import Attest

grader = Attest()                                   # needs ANTHROPIC_API_KEY by default
report = grader.evaluate(run, checks=("faithfulness",))

result = report.by("faithfulness")
print(result.score, result.metadata["claims_checked"], result.metadata["claims_total"])
for finding in result.findings:
    print(finding.verdict, finding.subject, "|", finding.evidence)
```

`run` is a `Trajectory`; [Getting started](../getting-started.md) shows one written as JSON and
[Integrations](../integrations.md) shows how to build one from LangGraph, LangChain or Haystack
messages. On the command line it's `attest run run.json --checks faithfulness`.

A claim with nothing to check it against is `unverifiable`, not `unsupported`: attest can't tell
a made-up fact from one that came from a tool call the run didn't record. If an answer is mostly
unverifiable, either the agent is inventing or your runs are missing tool outputs, and both are
worth knowing. `report.claim_coverage` gives the share of claims that were checked, and
`VerdictPolicy(min_claim_coverage=...)` sends low-coverage runs to review.

## Catch failed actions reported as success

A failed tool call followed by a confident "done" is caught by the
[tool-use check](../checks/tool-use.md). It follows each tool error to see whether the agent
retried it, used a declared fallback, or told the user. With `check_answer=True`, a model reads
the final answer to tell an error the agent reported from one it covered up:

```python
from attest import Attest, Step, ToolCall, Trajectory

run = Trajectory(
    task="Refund order 1042.",
    allowed_tools=["lookup_order", "refund"],
    steps=[
        Step(tool_call=ToolCall(
            name="lookup_order", arguments={"id": 1042},
            output="Order 1042: 59.00 USD, paid",
        )),
        Step(tool_call=ToolCall(
            name="refund", arguments={"id": 1042},
            output="Error: payment gateway timeout",
        )),
    ],
    final_answer="Your refund of 59.00 USD has been processed.",
)

result = Attest().tool_use(run, check_answer=True)
for finding in result.failures:
    print(finding.subject, finding.verdict)       # refund error_claimed_success
```

A tool error the answer reported as success blocks by default. Without a key, leave out
`check_answer`: the check still flags the unrecovered error (`error_silent`, sent to review),
but can't tell whether the answer hid it.

Tool errors are detected from the output text unless you set `ToolCall.is_error`. Set it when
you know the status; a structured failure such as an HTTP 500 body can otherwise be misread.

## Compare with a plain LLM judge on your own runs

`attest demo` grades the same run twice, once with a plain "is this answer good?" judge and once
with attest, and says which caught what:

```bash
attest demo examples/trajectory.json
```

This shows the difference on one run. It isn't a measurement of attest's accuracy, which hasn't
been measured on a labelled benchmark yet; see [Limitations](../limitations.md).

## Next

- [How to evaluate AI agents](evaluate-ai-agents.md)
- [Faithfulness check reference](../checks/faithfulness.md)
- [Prompt injection in agent tool outputs](prompt-injection-tool-outputs.md)
