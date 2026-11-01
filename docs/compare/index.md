---
title: "AI agent evaluation tools compared: DeepEval, Ragas, Phoenix"
description: "A sourced comparison of AI agent evaluation tools: attest, DeepEval, Ragas, LangSmith, Arize Phoenix, TruLens and promptfoo, and what each is good at."
---

# AI agent evaluation tools compared

There are many good AI evaluation tools, and most do more than attest. This page sets attest
next to the agent evaluation tools people most often ask about, says what each is good at, and
says plainly where attest is narrower.

!!! note "How this was checked"
    Each tool's features below come from its own repository or documentation, linked in
    [Sources](#sources), as checked on **1 November 2026**. These projects move quickly; check
    their docs for anything you plan to rely on. If something here is out of date, please
    [open an issue](https://github.com/peace-orefejo/attest/issues).

## The short version

- **attest** checks one recorded agent run against its own tool outputs: each claim in the
  answer, each tool call and error, injected instructions in what the agent read, and the
  agent's role. It's a Python library and a command line that print JSON. It has no UI, no
  tracing and no dataset management, and its own accuracy hasn't been measured on a labelled
  benchmark yet.
- **DeepEval** is a broad, pytest-style evaluation framework with many metrics, including RAG,
  agentic and conversational ones, and a hosted platform, Confident AI.
- **Ragas** is an evaluation toolkit with RAG metrics, agent and tool-call metrics, and test
  data generation.
- **LangSmith** is LangChain's platform for tracing, evaluating and monitoring LLM apps and
  agents, with datasets, experiments, online evaluation and human annotation.
- **Arize Phoenix** is an observability platform you can run yourself, with OpenTelemetry
  tracing, evaluations, datasets, experiments and a prompt playground.
- **TruLens** evaluates and tracks LLM apps and agents, with OpenTelemetry tracing and agent
  evaluators.
- **promptfoo** is a CLI and library for testing prompts and models and for red teaming LLM
  apps.

If you need dashboards, production monitoring or a wide metric catalogue, use one of the
platforms or frameworks. attest is for one question they answer less directly: **does what the
agent told the user match what its tools actually returned?** It can run alongside any of them.

## At a glance

| Tool | License | Form | Agent and tool-call evaluation | UI and tracing |
|---|---|---|---|---|
| attest | AGPL-3.0 | Python library and CLI | Claims checked against tool outputs; allowed tools and error recovery; injection in tool outputs; role adherence | None |
| DeepEval | Apache-2.0 | Python framework | Task Completion, Tool Correctness, Argument Correctness, Plan Adherence and other agentic metrics | Tracing with `@observe`; hosted platform (Confident AI) |
| Ragas | Apache-2.0 | Toolkit | Tool Call Accuracy, Tool Call F1, Agent Goal Accuracy, Topic Adherence | Integrates with observability tools |
| LangSmith | Platform; SDK is MIT | Hosted platform, with self-hosting on the Enterprise plan | Offline and online evaluators: code, LLM-as-judge, human, pairwise; trajectory evaluators in `agentevals` | Yes, hosted |
| Arize Phoenix | Elastic License 2.0 | Self-hostable platform | Evaluators including Tool Invocation, Tool Selection and Faithfulness | Yes, OpenTelemetry |
| TruLens | MIT | Library | Agent evaluators such as ToolSelection, ToolCalling and PlanAdherence | Yes, OpenTelemetry |
| promptfoo | MIT | CLI and library | Evals of prompts and models; red teaming | Local web viewer (`promptfoo view`) |

## How attest's approach differs

Many metrics in these tools ask a model to score an output, an approach usually called
**LLM-as-a-judge**. DeepEval's README, for example, says its metrics "use LLM-as-a-judge and
other NLP models". That is flexible: one judge prompt can score almost anything.

attest also uses a model, but gives it a narrower job. It splits the answer into claims and asks,
for each one, whether the recorded tool outputs support it. The grading model never sees the
agent's reasoning, and every finding quotes the tool output it rests on. Tool use and the
injection scan don't use a model at all. The trade-off is scope: attest grades tool-grounded
correctness and little else. It doesn't score tone, helpfulness, relevance or retrieval
quality, and it can't check a claim the tools never spoke to.

Several of the tools above also have groundedness or faithfulness metrics (DeepEval's
Faithfulness and Hallucination, Ragas's Faithfulness, Phoenix's Faithfulness, TruLens's
Groundedness). Those usually compare an answer with retrieved context. attest's evidence is the
agent's tool outputs and artifacts, kept per call, and it adds the agent-specific checks around
them: whether each call was allowed, whether a failed call was retried, replaced or reported,
and whether the answer claimed success for a call that failed.

## Where attest is narrower

- **No UI, tracing or monitoring.** attest reads a recorded run and prints JSON. It doesn't
  capture traces, store results, or watch production traffic. LangSmith, Phoenix, TruLens and
  Confident AI do.
- **No dataset or experiment management.** You keep your runs; attest grades them and
  `attest stats` gives a pass rate with a confidence interval.
- **A small set of checks.** No RAG retrieval metrics, no conversational metrics, no synthetic
  data generation, no red-teaming attack generation.
- **Accuracy not yet measured.** attest's own accuracy hasn't been measured on a labelled
  benchmark; the benchmark that will measure it per check is
  [being built](https://github.com/peace-orefejo/attest/tree/main/benchmarks). Some other tools
  publish results for their judges (TruLens's README, for example, reports groundedness results
  on LLM-AggreFact); attest doesn't have any yet.
- **Trusts the record.** A fabricated tool output backs a fabricated claim. See
  [Limitations](../limitations.md).
- **Copyleft license.** attest is AGPL-3.0. Using it inside your own tests and CI is
  straightforward; distributing a modified version, or running one as a network service,
  requires releasing its source under the same license. The other tools here use permissive
  licenses or, for Phoenix, the Elastic License 2.0.

## Each tool in more detail

### DeepEval

An open-source framework for evaluating LLM apps, used like pytest (`assert_test` and
`deepeval test run`). Its README lists RAG metrics (including Faithfulness and Contextual
Precision), agentic metrics (Task Completion, Tool Correctness, Goal Accuracy, Step Efficiency,
Plan Adherence, Plan Quality, Tool Use, Argument Correctness), multi-turn metrics (including
Role Adherence and Turn Faithfulness), a Hallucination metric, and G-Eval and DAG for custom
LLM-as-a-judge metrics. Tracing uses an `@observe` decorator, and the hosted Confident AI
platform runs evals on production traces. Red teaming, including prompt injection attacks, is in
a companion project, DeepTeam. **Good at:** breadth of metrics and a familiar unit-test workflow.
See also [attest vs DeepEval](deepeval.md).

### Ragas

An Apache-2.0 toolkit for evaluating LLM applications. Its metric list covers retrieval
(Context Precision, Context Recall, Faithfulness, Response Relevancy and others), agents and
tool use (Topic Adherence, Tool Call Accuracy, Tool Call F1, Agent Goal Accuracy), natural
language comparison (BLEU, ROUGE, semantic similarity and others), SQL, and general-purpose
rubric scoring. It also generates test datasets. **Good at:** RAG evaluation and test set
generation.

### LangSmith

LangChain's platform, which its SDK describes as helping "debug, evaluate, and monitor your
language models and intelligent agents", and which "works with any LLM Application". Its
evaluation docs cover offline evaluation on datasets and online evaluation of production traces,
with human, code, LLM-as-judge and pairwise evaluators, experiments and annotation queues.
Self-hosting is an add-on to the Enterprise plan. LangChain's open-source `agentevals` package
adds trajectory evaluators: match modes (strict, unordered, subset, superset) and an LLM-as-judge
trajectory evaluator. **Good at:** a full hosted workflow from tracing to datasets to human
review, especially for LangChain and LangGraph users.

### Arize Phoenix

An observability platform for experimentation, evaluation and troubleshooting, under the Elastic
License 2.0. It provides OpenTelemetry-based tracing, LLM evals, versioned datasets,
experiments, a prompt playground and prompt management, and runs locally, in a container or on
Kubernetes. Its `phoenix-evals` package includes evaluators such as Faithfulness, Tool
Invocation, Tool Selection and Tool Response Handling, alongside code-based checks. **Good at:**
self-hosted tracing and evaluation in one place.

### TruLens

An MIT-licensed tool for "Evaluation and Tracking for LLM Experiments and AI Agents", with
OpenTelemetry-native tracing. It lists agent evaluators (LogicalConsistency,
ExecutionEfficiency, PlanAdherence, PlanQuality, ToolSelection, ToolCalling, ToolQuality) and
RAG metrics such as groundedness and context relevance, with a trace view and a leaderboard for
comparing app versions. **Good at:** tracing plus feedback metrics for RAG and agent apps.

### promptfoo

An MIT-licensed "CLI and library for evaluating and red-teaming LLM-based apps", installed with
npm, npx, Homebrew or pip. It compares prompts and models side by side in a local web viewer,
runs in CI/CD, and does red teaming and vulnerability scanning. Its README says it is now part of OpenAI and remains open source and MIT
licensed. **Good at:** prompt and model comparisons and security testing before release.

## Choosing

- To see and debug what agents do in production: LangSmith, Phoenix or TruLens.
- For a wide catalogue of metrics in a pytest workflow: DeepEval.
- For RAG metrics and synthetic test sets: Ragas.
- To compare prompts and models and red-team an app: promptfoo, or DeepTeam.
- To check that an agent's answer and actions match its recorded tool outputs, with a quote for
  every failure and JSON you can gate CI on: attest, alongside any of the above.

## Sources

Checked on 1 November 2026.

- DeepEval: [README](https://github.com/confident-ai/deepeval) (license, metric list,
  LLM-as-a-judge, pytest workflow, tracing, Confident AI).
- DeepTeam: [README](https://github.com/confident-ai/deepteam) (red teaming, prompt injection
  attacks, built on DeepEval).
- Ragas: [repository](https://github.com/explodinggradients/ragas) (license, test data
  generation) and
  [list of available metrics](https://github.com/explodinggradients/ragas/blob/main/docs/concepts/metrics/available_metrics/index.md).
- LangSmith: [SDK README](https://github.com/langchain-ai/langsmith-sdk),
  [evaluation concepts](https://github.com/langchain-ai/docs/blob/main/src/langsmith/evaluation-concepts.mdx),
  [self-hosting](https://github.com/langchain-ai/docs/blob/main/src/langsmith/self-hosted.mdx)
  and [agentevals](https://github.com/langchain-ai/agentevals).
- Arize Phoenix: [README](https://github.com/Arize-ai/phoenix) and
  [phoenix-evals](https://github.com/Arize-ai/phoenix/tree/main/packages/phoenix-evals).
- TruLens: [README](https://github.com/truera/trulens).
- promptfoo: [README](https://github.com/promptfoo/promptfoo).
- attest: [Limitations](../limitations.md) and the
  [benchmark README](https://github.com/peace-orefejo/attest/blob/main/benchmarks/README.md).
