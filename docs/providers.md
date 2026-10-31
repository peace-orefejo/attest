---
description: "Grade AI agents with Anthropic, OpenAI or Gemini models in attest, choose a model, and bring your own LLM client."
---

# Models and providers

attest grades with Anthropic, OpenAI or Gemini models. Pick one when you create the `Attest` grader:

```python
from attest import Attest

Attest()                                        # Anthropic, default model
Attest(provider="openai", model="gpt-5.6-luna")
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

## Your own client

Pass any object that implements the `LLMClient` protocol in `attest.llm` as `client=`, to
route grading through your own gateway, cache or rate limiter.
