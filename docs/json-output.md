---
description: "The JSON every attest command prints: the versioned envelope, exit codes, fields per command, jq examples and JSON Schemas."
---

# JSON output

Every `attest` command prints one JSON document on stdout, and nothing else. All but
`attest schema` wrap their result the same way:

```json
{"schema_version": "1", "command": "run", "ok": true, "data": { ... }}
```

When a command can't run, `ok` is `false` and `error` replaces `data`:

```json
{"schema_version": "1", "command": "role", "ok": false,
 "error": {"code": "missing_api_key", "message": "Set the anthropic API key ..."}}
```

`error.code` is `invalid_input` or `missing_api_key`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The command ran. |
| `1` | A required API key is missing. |
| `2` | The input or an option is invalid. |
| `3` | A budget stopped `attest run`. The runs graded so far are still printed. |

The exit code says whether the command ran, not whether the agent passed.

## What `data` holds

| Command | `data` |
|---|---|
| `run` | `trajectories`: one entry per graded run, each a `task` and its `report`. Then `total` (runs in the file), `evaluated` (runs graded), `passed` (runs whose report passed), `mean_overall_score`, `usage` (calls and tokens), and `budget_exceeded`: why a budget stopped the run, or `null`. |
| `tools`, `injection`, `role` | `trajectories`: one entry per run, each a `task` and its `result` |
| `review` | A [`ReviewResult`](code-review/outputs.md#reviewresult) |
| `demo` | `comparisons`: one per run, with `task`, `answer`, the plain LLM judge's verdict (`judge`), attest's faithfulness result (`attest`), and `outcome`: `caught` (attest caught a false claim the judge passed), `both_caught`, `both_passed` or `judge_only` |
| `stats` | `rate`, `low`, `high`, `n` |
| `models` | `provider`, `source` (`live` or `curated`), `models` |

A `report` holds `results` (one per check), `overall_score` and `passed`. Each result and
finding has the fields described in [How it works](concepts.md#results-and-findings).

From Python, `report.model_dump_json()` gives the same JSON as one `report` in `attest run`'s
output, and a check's `result.model_dump_json()` the same as one `result` from `attest tools`,
`injection` or `role`.

## Examples

```bash
# The failed claims, with the evidence against them
attest run run.json | jq '.data.trajectories[].report.results[].findings[]
  | select(.severity == "fail") | {subject, reason, evidence}'

# Fail a CI step unless every run passed
attest run runs.jsonl | jq -e '.ok and .data.passed == .data.total'
```

## Schemas

`attest schema <command>` prints the JSON Schema for a command's output. The same schemas are
published as `schemas/v1/<command>.json` on this site, for example
[run.json](schemas/v1/run.json) and [error.json](schemas/v1/error.json).

Within `schema_version` `"1"`, fields may be added but never removed or redefined.
