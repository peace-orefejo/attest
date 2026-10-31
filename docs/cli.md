---
description: "Every attest command and option: run, tools, injection, role, review, demo, stats, models and schema."
---

# Command line

Run commands take a `.json` file with one run, or a `.jsonl` file with one run per line. Every
command prints [JSON](json-output.md). Commands that use a model accept `--provider` (`-p`) and
`--model` (`-m`).

| Command | Does | Needs a key? |
|---|---|---|
| `attest run FILE` | Grades every run in FILE with the chosen checks. | Yes |
| `attest tools FILE` | Tool-use check. `--appropriate` adds a model check of each tool choice. | Only with `--appropriate` |
| `attest injection FILE` | Prompt-injection scan. `--deep` checks whether the agent obeyed. | Only with `--deep` |
| `attest role FILE` | Role-adherence check. | Yes |
| `attest review FILE` | Checks an AI code reviewer's outputs. | Yes |
| `attest demo [FILE]` | A plain LLM judge and attest side by side. FILE defaults to `examples/trajectory.json`. | Yes |
| `attest stats PASSED N` | A pass rate with a 95% confidence interval. | No |
| `attest models PROVIDER` | A provider's models: fetched live when its key is set (`source: live`), a curated list otherwise. | No |
| `attest schema [COMMAND]` | The JSON Schema of a command's output; `error` for the error envelope, nothing for all. | No |

## `attest run`

```bash
attest run runs.jsonl --checks faithfulness,tool_use,injection,role > report.json
```

| Option | Default | Meaning |
|---|---|---|
| `--checks` | `faithfulness,tool_use` | Any of `faithfulness`, `tool_use`, `injection`, `role`. |
| `--kind` | `factual` | Answer kind: `factual`, `plan`, `code` or `auto`. |
| `--appropriate` | off | Add the model tool-choice check. |
| `--max-calls`, `--max-tokens` | none | Stop before going over this budget (exit code 3). |
| `--cache-dir PATH` | none | Reuse grading verdicts across runs. |

Injection inside `attest run` is always deep (it checks whether the agent obeyed a payload), so
it makes model calls. Use `attest injection` for a scan without a key.

## `attest injection`

| Option | Meaning |
|---|---|
| `--deep` | Check with a model whether the agent obeyed each payload. |
| `--patterns FILE` | Add regex patterns from a JSON file. |
| `--patterns-only` | Use only `--patterns`, not the built-in detectors. Needs `--patterns`. |
| `--no-extract-files` | Don't extract embedded files before scanning. |
| `--allow-paths` | Read local files the run refers to by path. |

## `attest review`

```bash
attest review review.json -g REVIEW.md --mode issue=strict
```

The file holds a [`PullRequest`](code-review/outputs.md#pullrequest) and its
[`ReviewOutput`](code-review/outputs.md#reviewoutput)s. Leave out `outputs` and attest
[writes the review](code-review/writing.md) first.

```json
{
  "pr": {"diffs": {"billing/cart.py": "--- a/billing/cart.py\n+++ b/billing/cart.py\n@@ ..."}},
  "outputs": [{"output_type": "issue", "text": "cart_total no longer checks for a missing user."}]
}
```

| Option | Default | Meaning |
|---|---|---|
| `-g`, `--guidelines PATH` | none | A file of [review rules](code-review/guidelines.md). Repeatable. |
| `--follow` / `--no-follow` | on | Drop outputs that break a review rule. |
| `--mode TYPE=MODE` | per type | Override a [gate mode](code-review/index.md#keep-or-drop-the-gate), e.g. `issue=strict`. Repeatable. |
| `--deep` / `--no-deep` | on | Confirm injection hits with the grading model and check which outputs obeyed them. |
