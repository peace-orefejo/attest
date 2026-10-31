# attest

**A reality-checker for AI agents.** attest grades an agent's answer against what its tools
actually returned. It catches made-up facts, misused tools and prompt-injection slips that a
"does this look good?" grader waves through.

```bash
pip install agent-attest      # the command and the import are both `attest`
attest run your-run.json      # prints JSON
```

Every command prints [JSON](json-output.md). Here the agent said Paris is larger than Berlin,
and attest quotes the tool output that shows it isn't:

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

## Why

Most agent evals ask another model whether the answer is good. A confident answer can pass that
even when a detail inside it is wrong; rewriting an agent's reasoning alone can raise an LLM
judge's false-positive rate by up to 90%
([Khalifa et al., 2026](https://arxiv.org/abs/2601.14691)).

attest never trusts what the agent says it did. Every tool call produced a real output, and
those outputs are the only evidence attest accepts.

![How attest checks an answer](assets/diagrams/how-it-works.svg){ .diagram }

## What it checks

| Check | Question | Needs a model? |
|---|---|---|
| [Faithfulness](checks/faithfulness.md) | Is every claim in the answer backed by a tool output? | Yes |
| [Tool use](checks/tool-use.md) | Did the agent call allowed tools and handle their errors? | No |
| [Prompt injection](checks/injection.md) | Did tool outputs carry hidden instructions, and did the agent obey them? | Only for `--deep` |
| [Role adherence](checks/role.md) | Did the agent stay inside its system prompt's job? | Yes |
| [Policies](checks/policies.md) | Did the run follow your project's own rules? | Only for semantic rules |

Scores come with [95% confidence intervals](concepts.md#scores-and-error-bars), so you can tell a
real improvement from noise.

## Code review mode

attest can also check the outputs of an AI code reviewer: flagged issues, diff summaries, group
summaries and answers to questions about a change. Each one is checked against the diff, and a
gate decides whether to keep or drop it. See [Code review mode](code-review/index.md).

## Next steps

- [Getting started](getting-started.md): install, set a key and grade your first run.
- [How it works](concepts.md): runs, claims, verdicts and scores.
- [Command line](cli.md): every command and flag.
- [JSON output](json-output.md): the shape of every command's output, with JSON Schemas.
- [Contributing](contributing.md): set up a dev environment and send a change.
