# Command line

Run commands take a `.json` file with one run, or a `.jsonl` file with one run per line. Every
command prints [JSON](json-output.md). Commands that use a model accept `--provider` (`-p`) and
`--model` (`-m`).

| Command | Does | Needs a key? |
|---|---|---|
| `attest run FILE` | Runs several checks and scores each run. | Yes |
| `attest tools FILE` | Tool-use check. `--appropriate` adds a model check of each tool choice. | Only with `--appropriate` |
| `attest injection FILE` | Prompt-injection scan. `--deep` checks whether the agent obeyed. | Only with `--deep` |
| `attest role FILE` | Role-adherence check. | Yes |
| `attest review FILE` | Checks an AI code reviewer's outputs. | Yes |
| `attest demo FILE` | A plain LLM judge and attest side by side. | Yes |
| `attest stats PASSED N` | A pass rate with a 95% confidence interval. | No |
| `attest models PROVIDER` | A provider's models. | No |
| `attest schema [COMMAND]` | The JSON Schema of a command's output. | No |

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
| `--cache-dir PATH` | none | Reuse judge verdicts across runs. |

## `attest injection`

| Option | Meaning |
|---|---|
| `--deep` | Check with a model whether the agent obeyed each payload. |
| `--patterns FILE` | Add regex patterns from a JSON file. `--patterns-only` drops the built-ins. |
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
| `--no-follow` | off | Don't drop outputs that break a review rule. |
| `--mode TYPE=MODE` | per type | Override a gate mode. Repeatable. |
| `--no-deep` | off | Skip the model confirmation of injection hits. |
