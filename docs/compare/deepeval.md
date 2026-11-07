---
title: "attest vs DeepEval: evaluating tool-using AI agents"
description: "attest vs DeepEval for AI agent evaluation: what each checks, how they grade, and when to use them together. Sources linked."
---

# attest vs DeepEval

[DeepEval](https://github.com/confident-ai/deepeval) is a broad, open-source framework for
evaluating LLM apps. attest focuses on one job: it checks a tool-using agent's answer and
actions against the outputs its tools actually returned. If you're looking for a DeepEval
alternative for that specific job, this page says what differs. For most teams the two are
complements, not substitutes.

DeepEval's features below come from its
[README](https://github.com/confident-ai/deepeval) and the
[DeepTeam README](https://github.com/confident-ai/deepteam), checked on 1 November 2026.

## Side by side

| | attest | DeepEval |
|---|---|---|
| License | Apache-2.0 | Apache-2.0 |
| Shape | Library and CLI that grade a recorded run and print JSON | pytest-style framework (`assert_test`, `deepeval test run`) and `evaluate()` |
| Scope | Tool-using agent runs and AI code review output | RAG, agentic, multi-turn, multimodal and custom metrics |
| Agent checks | Claims against tool outputs; allowed tools; error recovery and errors reported as success; injection in tool outputs; role adherence; project policies | Task Completion, Tool Correctness, Argument Correctness, Goal Accuracy, Step Efficiency, Plan Adherence, Plan Quality, Tool Use |
| Grounding | Each claim checked against the run's tool outputs and artifacts | Faithfulness and Hallucination compare the output with provided context |
| How it grades | A model sees one claim batch and the evidence, never the agent's reasoning; tool use and the injection scan need no model | Metrics "use LLM-as-a-judge and other NLP models"; G-Eval and DAG for custom judge metrics |
| Output | A pass, review or block verdict with a quote for each failure | Metric scores with thresholds and reasons |
| Prompt injection | Scans tool outputs and files for payloads; optional check that the agent obeyed | Red teaming, including prompt injection attacks, in the companion DeepTeam project |
| UI and tracing | Runs alongside your tracing tool; output is JSON | `@observe` tracing; hosted Confident AI platform |

## Where DeepEval is the better fit

- You want many metrics in one framework: RAG, conversational, multimodal and custom
  LLM-as-a-judge metrics.
- You want tests that read like unit tests and run under pytest.
- You want hosted dashboards, production trace evaluation and annotation through Confident AI.
- You want to generate adversarial attacks against your app (DeepTeam).

## Where attest is the better fit

- You want each failure tied to a quote from a specific tool output, so a person can check it in
  seconds.
- You want tool errors followed through the run: retried, replaced by a declared fallback,
  reported, ignored, or reported as success when they failed.
- You want to scan fetched pages, files and images for injected instructions without an API
  key, with an optional model-backed deep check of whether the agent acted beyond what it was
  asked to do.
- You want a `pass`, `review` or `block` verdict and JSON you can gate CI on with `jq`.

## Using both

attest reads a plain `Trajectory`, and DeepEval reads its own test cases, so the same recorded
run can go through both. A common split is DeepEval for broad quality metrics and attest as a
gate on whether the answer is supported by the tool outputs:

```python
from attest import Attest

report = Attest().evaluate(run, checks=("faithfulness", "tool_use", "injection"))
if report.verdict == "block":
    raise SystemExit(f"blocked by {report.blocking}")
```

## Using them together

DeepEval covers a wide range of metrics and a hosted platform; attest adds a per-claim check
against the agent's own tool outputs and a pass, review or block gate. Many teams can run both:
DeepEval for broad metrics, attest as the evidence check in CI. See the full
[comparison of AI agent evaluation tools](index.md).
