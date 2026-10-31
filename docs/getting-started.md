---
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

The tool-use check and the shallow injection scan run without any key.

## Describe a run

attest grades a **run**: the task, the tool calls the agent made, what each tool returned, and
the final answer. Save one as JSON:

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

The claim that Paris is larger comes back as an `unsupported` finding, with the tool output that
contradicts it in `evidence`. [JSON output](json-output.md) describes every field.

## From Python

```python
from attest import Attest, Trajectory

run = Trajectory.model_validate_json(open("run.json").read())
judge = Attest()

report = judge.evaluate(run)
print(report.passed, report.overall_score)
for finding in report.by("faithfulness").failures:
    print(finding.subject, "->", finding.reason)
```

Single checks have their own methods:

```python
judge.tool_use(run)                # offline
judge.injection(run, deep=True)    # deep mode checks whether the agent acted on a payload
judge.role_adherence(run)
```

Results are Pydantic models, so `report.model_dump_json()` gives the same JSON the command line
prints.

Next, read [How it works](concepts.md) to see what each verdict means.
