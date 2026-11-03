---
title: "Models and providers: Anthropic, OpenAI and Gemini"
description: "Grade AI agents with Anthropic, OpenAI or Gemini models in attest, choose a model, and bring your own LLM client."
---

# Models and providers

attest grades with Anthropic, OpenAI or Gemini models. Pick one when you create the `Attest` grader:

```python
from attest import Attest

Attest()                                        # Anthropic, default model
Attest(provider="openai", model="gpt-6.1-terra")
Attest(provider="gemini")
Attest.models("openai")                         # models you can use
```

On the command line, pass `--provider` and `--model` to any command that grades with a model.

| Provider | Install | Key |
|---|---|---|
| `anthropic` | included | `ANTHROPIC_API_KEY` |
| `openai` | `pip install "agent-attest[openai]"` | `OPENAI_API_KEY` |
| `gemini` | `pip install "agent-attest[gemini]"` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |

Keys are read from the environment or from a `.env` file in the working directory or a parent.
You can also pass the chosen provider's key as `key=` to `Attest`.

Each provider defaults to a small, fast model, so grading a run costs cents. A stronger model
catches subtler errors. Compare models on your own labeled runs before you switch, and use
[`difference_is_real`](concepts.md#pass-rates-and-confidence) to check that the gap isn't noise.

## Reasoning

Newer models can reason (think) before they answer. Reasoning tokens are billed as output tokens
and count against each call's output limit, so they are the largest lever on what a grading run
costs. attest lets you choose how much the judge may reason:

```python
Attest(reasoning="auto")                                     # the default
Attest(reasoning="off")
Attest(reasoning={"faithfulness": "medium", "default": "auto"})
```

| Level | What it does |
|---|---|
| `auto` (default) | The provider's adaptive thinking decides, at low effort. An easy claim gets little or no reasoning; a hard one gets more. |
| `off` | Turns reasoning off where the model allows it, otherwise uses its lowest level. Cheapest; least careful on hard claims. |
| `low`, `medium`, `high` | Sets the reasoning effort. Higher levels can catch subtler errors and cost more. |

A mapping sets a level per check (`faithfulness`, `tool_use`, `injection`, `role`, `policy`,
`guidelines`, `writer`, `judge`) or per call site, such as `faithfulness.verify` or
`guidelines.confirm`, with `"default"` for the rest. The most specific key wins.
`ReasoningPolicy(default=..., checks={...})` is the same thing as a model. On the command line,
pass `--reasoning` to any command that uses a model, for example `--reasoning off` or
`--reasoning faithfulness=medium,default=auto`.

Each report records the level every call site used in `metadata["reasoning"]`, so you can
compare levels on the same runs. A run keeps one level per call site, which keeps the
provider's prompt cache valid between calls.

### What each model receives

| Model | `auto` | `off` | `low` / `medium` / `high` |
|---|---|---|---|
| Claude Haiku 5.5 | adaptive thinking, effort `low` | thinking disabled, effort `low` | adaptive thinking at that effort |
| Claude Sonnet 5.5 | adaptive thinking, effort `low` | thinking only between tool calls (none here), effort `low` | adaptive thinking at that effort |
| Claude Opus 5.5 | effort `low` | effort `low` (its thinking can't be turned off) | that effort |
| OpenAI `gpt-6-*`, `gpt-6.1-*` | `reasoning_effort` `low` (no adaptive mode) | `reasoning_effort` `none` | that effort |
| Gemini 3.8 Flash, 3.5 Flash-Lite, 4 Argon | dynamic thinking (`thinking_budget=-1`) | the lowest thinking level (`MINIMAL` on Flash and Flash-Lite, `LOW` on Argon) | that thinking level |

Any other model, including older ones and Claude Fable 5.1, receives no reasoning setting and
behaves exactly as before. On OpenAI, `temperature` is only sent when reasoning is off, since
reasoning models don't accept it. The table lives in `attest.llm.thinking`.

Whenever a call may reason, attest raises its output limit by an allowance for the level (4,096
tokens for `auto` and `low`, 8,192 for `medium`, 16,384 for `high`, up to 20,000 in total), so
reasoning can't use up the room the answer needs. The limit is a ceiling, not a charge: you pay
only for the tokens the model writes. Reasoning tokens are included in the output tokens attest
reports in `usage`, for every provider.

If a model still stops at its output limit before it finishes, that call is reported as
`unchecked`, like any other failed judge call, and the run or review carries on.

## Your own client

Pass any object that implements the `LLMClient` protocol in `attest.llm` as `client=`, to
route grading through your own gateway, cache or rate limiter. A custom client receives the
same arguments as before and no reasoning setting; configure reasoning in the client itself.
