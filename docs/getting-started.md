---
title: "Getting started: evaluate your first AI agent run"
description: "Install attest, set an API key and grade your first AI agent run from the command line or Python in a few minutes."
---

# Getting started

## Install

```bash
pip install agent-attest
```

It grades with Anthropic models by default. For OpenAI or Gemini, see
[Models and providers](providers.md). To scan PDFs and images for injection, install
`"agent-attest[files]"`; image OCR also needs `tesseract`.

## Set a key

Checks that use a model read the provider's key from the environment. A `.env` file in the
working directory or a parent works too.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

`attest tools` and `attest injection` (without `--deep`) run without a key. `attest run` always
needs one.

## Describe a run

attest grades a **run**: the task, the tool calls the agent made, what each tool returned, and
the final answer. In Python a run is a `Trajectory`. Save this one as `run.json`:

```json
{
  "task": "What is the population of Paris, and is it larger than Berlin?",
  "allowed_tools": ["web_search", "get_population"],
  "steps": [
    {
      "thought": "Look up both cities.",
      "tool_call": {
        "name": "get_population",
        "arguments": {"city": "Paris"},
        "output": "Paris population (city proper): 2,103,000"
      }
    },
    {
      "tool_call": {
        "name": "get_population",
        "arguments": {"city": "Berlin"},
        "output": "Berlin population (city proper): 3,677,000"
      }
    }
  ],
  "final_answer": "Paris has about 2.1 million people. It is larger than Berlin."
}
```

A file ending in `.jsonl` holds one run per line.

## Grade it

```bash
attest run run.json > report.json
```

`report.json` holds one report for the run, with a result for each check (faithfulness and tool
use by default). The claim that Paris is larger comes back as a finding with
`"verdict": "unsupported"` and the contradicting tool output in `evidence`.
[JSON output](json-output.md) describes every field.

## From Python

```python
from attest import Attest, Trajectory

run = Trajectory.model_validate_json(open("run.json").read())
grader = Attest()

report = grader.evaluate(run)
print(report.verdict, report.overall_score)   # verdict: pass, review or block
for finding in report.by("faithfulness").failures:
    print(finding.subject, "->", finding.reason)
```

`evaluate()` runs faithfulness and tool use. Pass `checks=` to choose others, or call a single
check directly:

```python
grader.evaluate(run, checks=("faithfulness", "tool_use", "injection", "role"))

grader.tool_use(run)                # no key needed
grader.injection(run, deep=True)    # deep: also check whether the agent obeyed a payload
grader.role_adherence(run)
```

Results are Pydantic models. `report.model_dump_json()` gives the same JSON as one
`data.trajectories[].report` in `attest run`'s output.

Next, read [How it works](concepts.md) to see what each verdict means.
