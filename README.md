<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/peace-orefejo/attest/main/docs/assets/brand/attest-logo-dark.svg">
  <img alt="attest" src="https://raw.githubusercontent.com/peace-orefejo/attest/main/docs/assets/brand/attest-logo.svg" height="64">
</picture>

<br>
<br>

**A reality-checker for AI agents.**<br>
Grade an agent's answer against what its tools actually returned.

<br>

[![PyPI](https://img.shields.io/pypi/v/agent-attest)](https://pypi.org/project/agent-attest/)
[![Python](https://img.shields.io/pypi/pyversions/agent-attest)](https://pypi.org/project/agent-attest/)
[![CI](https://github.com/peace-orefejo/attest/actions/workflows/ci.yml/badge.svg)](https://github.com/peace-orefejo/attest/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[**Documentation**](https://peace-orefejo.github.io/attest/) ·
[Getting started](https://peace-orefejo.github.io/attest/getting-started/) ·
[JSON output](https://peace-orefejo.github.io/attest/json-output/) ·
[Code review mode](https://peace-orefejo.github.io/attest/code-review/)

</div>

<br>

## Quick start

attest grades a **run**: a JSON record of one task, with the question, each tool call and what
it returned, and the agent's final answer ([example](examples/trajectory.json)).

```bash
pip install agent-attest
export ANTHROPIC_API_KEY=sk-ant-...
attest run your-run.json
```

Every command prints JSON. A false claim comes back with the tool output that contradicts it:

```json
{
  "severity": "fail",
  "verdict": "unsupported",
  "subject": "Paris is larger than Berlin",
  "reason": "The evidence shows Berlin has a population of 3,677,000 while Paris has 2,103,000, meaning Berlin is larger than Paris, not the other way around.",
  "evidence": "Paris population (city proper): 2,103,000",
  "step": null,
  "metadata": {}
}
```

<br>

## Why attest

Most agent evals ask another model whether the answer looks good. A confident answer can pass
even when a detail inside it is wrong; rewriting an agent's reasoning alone can raise an LLM
judge's false-positive rate by up to 90%
([Khalifa et al., 2026](https://arxiv.org/abs/2601.14691)).

attest checks each claim against the real tool outputs instead. Its grading model sees only the
claim and the evidence, never the agent's reasoning.

<br>

## What it checks

| Check | Question | API key |
|:---|:---|:---:|
| **Faithfulness** | Is every claim backed by a tool output? | ✓ |
| **Tool use** | Were the tools allowed, and were their errors handled? | — |
| **Prompt injection** | Did tool outputs carry hidden instructions, and were they obeyed? | `--deep` only |
| **Role adherence** | Did the agent stay inside its system prompt's job? | ✓ |
| **Policies** (Python only) | Did the run follow your project's own rules? | `evidence` and `rubric` rules only |

`attest stats` turns a pass count into a rate with a 95% confidence interval, so you can tell a
real improvement from noise.

<br>

## Usage

**Command line**

```bash
attest run run.json          # faithfulness + tool use, with an overall score
attest tools run.json        # tool use only (no key)
attest injection run.json    # injection scan only (no key)
attest review review.json    # check an AI code reviewer's outputs
```

**Python**

```python
from attest import Attest

grader = Attest()                      # or Attest(provider="openai" | "gemini")
report = grader.evaluate(run)

print(report.passed, report.overall_score)
```

In Python a run is a `Trajectory`. [`examples/quickstart.py`](examples/quickstart.py) builds
one by hand, and `from_langgraph_messages` and
`from_haystack_messages` convert LangGraph and Haystack runs.

**Code review**

```python
result = Attest().review(pr, outputs, guidelines="REVIEW.md")
post = result.filter(outputs)         # the outputs worth showing
```

<br>

## Install options

| Install | Adds |
|:---|:---|
| `pip install agent-attest` | Anthropic |
| `pip install "agent-attest[openai]"` | OpenAI |
| `pip install "agent-attest[gemini]"` | Gemini |
| `pip install "agent-attest[files]"` | PDF and image scanning for injection |
| `pip install "agent-attest[all]"` | Everything |

<br>

## Contributing

```bash
uv sync
uv run pytest
```

Tests run offline with no API key. See [CONTRIBUTING.md](CONTRIBUTING.md).

<br>

## License

Copyright © 2026 Adepeju Orefejo. Licensed under the [GNU AGPL v3.0](LICENSE): you can use,
modify and share attest, but any version you distribute or run as a network service must be
released under the same license, with its source. Versions 0.7.0 and earlier were MIT.
