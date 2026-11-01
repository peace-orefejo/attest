---
title: "How to evaluate AI agents: what to measure and how"
description: "A practical guide to AI agent evaluation: what to measure in a tool-using agent's run, why evidence-grounded checks beat answer-only grading, and a runnable example."
---

# How to evaluate AI agents

An AI agent doesn't just answer; it calls tools, reads what they return and then answers from
that. Evaluating an agent means checking that whole run, not only the final text. This guide
covers what to measure, why grading against the tool outputs matters, and how attest does it.

## What to measure

A run has four parts worth checking separately, because each fails in its own way:

| What can go wrong | Example | How to check it |
|---|---|---|
| **The answer isn't backed by the tools** | The search returned 2.1 million; the answer says 2.4 million. | Split the answer into claims and check each against the tool outputs. |
| **The tools were misused** | The agent called a tool it wasn't allowed to, or a call failed and the answer said it worked. | Compare each call with the allowed tools, and follow each error to see whether it was retried, replaced or reported. |
| **A tool output steered the agent** | A fetched web page told the agent to email the user's data somewhere. | Scan everything the agent read for instructions, then check whether the agent acted on one. |
| **The agent left its job** | A support agent wrote code, or was talked into ignoring its system prompt. | Compare what the agent did with the job its system prompt describes. |

Other things matter too, such as latency, cost and whether the user's task was done at all.
Those are usually measured from traces and outcomes; this guide is about correctness against
evidence.

## Why ground the evaluation in evidence

The common shortcut is an **LLM-as-a-judge**: give another model the question, the agent's
reasoning and its answer, and ask whether the answer is good. That works for tone and
helpfulness, but it is weak at catching one wrong number inside a confident, well-argued answer.
Rewriting an agent's reasoning alone can raise an LLM judge's false-positive rate by up to 90%
([Khalifa et al., 2026](https://arxiv.org/abs/2601.14691)).

A tool-using agent leaves something better than its own account of events: the tool outputs. An
evidence-grounded check asks a narrower question for each claim, "does this tool output support
this sentence?", and never lets the agent's reasoning into that question. The answer can then
be traced to a quote, which a person can check in seconds.

This isn't judge-free. Deciding whether a sentence is supported still takes a model, and that
model can be wrong. What changes is how much it sees and how much room it has to be persuaded.

## How attest evaluates an agent run

attest takes a **run** (in Python, a `Trajectory`): the task, the allowed tools, each tool call
with its output, and the final answer. Each check compares part of the run with the tool
outputs and returns findings, and every finding gets a disposition of `pass`, `review` or
`block`. The report's `verdict` is the strictest one, so one unsupported claim can't be averaged
away by good scores elsewhere. See [How it works](../concepts.md) for the details.

| Check | What it measures | Needs a model? |
|---|---|---|
| [Faithfulness](../checks/faithfulness.md) | Each claim in the answer against the tool outputs | Yes |
| [Tool use](../checks/tool-use.md) | Allowed tools, error handling and recovery | No (yes to read the answer for unreported errors) |
| [Prompt injection](../checks/injection.md) | Instructions hidden in tool outputs, and whether the agent obeyed | Only for `deep=True` |
| [Role adherence](../checks/role.md) | Whether the agent stayed inside its system prompt's job | Yes |
| [Policies](../checks/policies.md) | Your project's own rules | Only for `evidence` and `rubric` rules |

## A runnable example

Install attest and set a key for the grading model:

```bash
pip install agent-attest
export ANTHROPIC_API_KEY=sk-ant-...
```

This agent looked up two populations correctly, then drew the wrong conclusion from them:

```python
from attest import Attest, Step, ToolCall, Trajectory

run = Trajectory(
    task="Which city is larger by population, Paris or Berlin?",
    allowed_tools=["get_population"],
    steps=[
        Step(tool_call=ToolCall(
            name="get_population", arguments={"city": "Paris"},
            output="Paris: 2,103,000 residents",
        )),
        Step(tool_call=ToolCall(
            name="get_population", arguments={"city": "Berlin"},
            output="Berlin: 3,677,000 residents",
        )),
    ],
    final_answer=(
        "Berlin has about 3.7 million residents and Paris about 2.1 million, "
        "so Paris is the larger city."
    ),
)

grader = Attest()
report = grader.evaluate(run)              # faithfulness and tool use

print(report.verdict)                      # block
for finding in report.by("faithfulness").failures:
    print(finding.subject, "->", finding.evidence)
```

attest splits the answer into claims. The population figures match the tool outputs; the claim
that Paris is the larger city is contradicted by them, so it comes back `unsupported` with the
tool output in `evidence`. Because an unsupported
claim blocks by default, the report's verdict is `block`.

The same run is in [`examples/quickstart.py`](https://github.com/peace-orefejo/attest/blob/main/examples/quickstart.py).
On the command line, save the run as JSON and use `attest run run.json`; every command prints
[JSON](../json-output.md).

## Evaluate many runs, not one

One run tells you about one run. To compare two prompts or two models, grade a set of recorded
runs and look at the pass rate with its uncertainty:

```bash
attest run evals/runs.jsonl > report.json
attest stats 41 50          # pass rate 0.82 with a 95% confidence interval
```

```python
from attest import difference_is_real

difference_is_real(41, 50, 35, 50)   # False: the gap is within noise
```

[Integrations](../integrations.md#in-ci) shows how to gate a CI build on the interval rather
than on a single noisy run.

## What evidence-grounded evaluation can't tell you

attest trusts that the recorded run is authentic and complete: a faked tool output backs a faked
claim, and a claim that rests on an unrecorded call comes back `unverifiable`. Its own accuracy
hasn't been measured on a labelled benchmark yet. Read [Limitations](../limitations.md) before
you gate releases on it, and check its results on your own labelled runs first.

## Next

- [Detecting hallucinations in tool-using agents](agent-hallucinations.md)
- [Prompt injection in agent tool outputs](prompt-injection-tool-outputs.md)
- [AI agent evaluation tools compared](../compare/index.md)
