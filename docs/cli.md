# Command line

The run commands take a `.json` file holding one run, or a `.jsonl` file with one run per line.
`attest review` takes a review file. Commands that grade with a model accept `--provider` (`-p`)
and `--model` (`-m`). Every command accepts `--json` to print machine-readable JSON instead of
text.

## Output

Without `--json`, the checking commands (`run`, `tools`, `injection`, `role`, `demo` and
`review`) print the same layout:

- a status line: `PASS`, `FAIL`, `KEEP` or `DROP n`, then a title and a one-line subtitle with
  the score and counts;
- a summary table, one row per check or per review output;
- the findings, aligned in columns: a mark, the verdict, where it was found (such as the step),
  and the claim, with the reason and the quoted evidence on the lines below.

Python code gets the same view from [`attest.show`](getting-started.md#results-are-objects).

## `attest run`

Run several checks and print a report with an overall score.

```bash
attest run run.json
attest run runs.jsonl --checks faithfulness,tool_use,injection,role
attest run run.json --kind code --json
```

| Option | Default | Meaning |
|---|---|---|
| `--checks` | `faithfulness,tool_use` | Comma-separated: `faithfulness`, `tool_use`, `injection`, `role`. |
| `--kind` | `factual` | Answer kind: `factual`, `plan`, `code` or `auto`. |
| `--appropriate` | off | Add the model tool-choice check (one call per tool call). |
| `--json` | off | Print JSON instead of text. |

## `attest tools`

The tool-use check alone. Needs no key unless you pass `--appropriate`.

```bash
attest tools run.json
```

## `attest injection`

The prompt-injection scan. Needs no key unless you pass `--deep`.

| Option | Meaning |
|---|---|
| `--deep` | Also check with a model whether the agent obeyed each payload. |
| `--patterns FILE` | Add named regex patterns from a JSON file. |
| `--patterns-only` | Use only `--patterns`, not the built-in detectors. |
| `--extract-files` / `--no-extract-files` | Extract embedded files before scanning (on by default). |
| `--allow-paths` | Read local files the run refers to by path. |

## `attest role`

The role-adherence check. Needs a key.

## `attest review`

Check every output of a code review against the diff and your review rules, and decide which to
keep. Needs a key.

```bash
attest review examples/code_review.json
attest review review.json -g REVIEW.md -g SECURITY.md
attest review review.json --mode issue=strict --no-deep --json
```

The file holds the pull request and the reviewer's outputs:

```json
{
  "pr": {
    "title": "Apply the user's discount in cart_total",
    "diffs": {"billing/cart.py": "--- a/billing/cart.py\n+++ b/billing/cart.py\n@@ ..."},
    "changed_files": ["billing/cart.py"]
  },
  "outputs": [
    {"output_type": "issue", "text": "cart_total no longer checks for a missing user, ..."},
    {"output_type": "canvas_answer", "question": "Does this change touch tax?", "text": "No."}
  ]
}
```

`pr` is a [`PullRequest`](code-review/outputs.md#pullrequest) and each output is a
[`ReviewOutput`](code-review/outputs.md#reviewoutput). Leave out `outputs` and attest
[writes the review](code-review/writing.md) first, then checks it.

| Option | Default | Meaning |
|---|---|---|
| `--guidelines`, `-g PATH` | none | A markdown file of [review rules](code-review/guidelines.md). Repeatable. Without one, the general standard is used. |
| `--follow` / `--no-follow` | `--follow` | Drop outputs that break a review rule. |
| `--mode TYPE=MODE` | per type | Override a gate mode, e.g. `--mode issue=strict`. Repeatable. |
| `--deep` / `--no-deep` | `--deep` | Confirm injection hits with a model and check whether outputs obeyed them. |
| `--json` | off | Print the `ReviewResult` as JSON. |

The text view shows the guidelines and the injection verdict, a table with one row per output
(type, gate, score, `KEEP` or `DROP`), then the reasons behind each dropped output.

## `attest demo`

Run a plain LLM judge and attest side by side on the same run, and say which one caught what.

```bash
attest demo examples/trajectory.json
attest demo examples/trajectory.json --json
```

## `attest stats`

A pass rate with a 95% confidence interval.

```bash
attest stats 41 50
attest stats 41 50 --json
```

## `attest models`

List a provider's models. The list is fetched live when the provider's key is set, and is a
curated shortlist otherwise.

```bash
attest models anthropic
attest models anthropic --json
```
