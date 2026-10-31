# JSON output

Every `attest` command prints one JSON document on stdout, and nothing else:

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
| `run` | `trajectories` (each a `task` and its `report`), `total`, `evaluated`, `passed`, `mean_overall_score`, `usage`, `budget_exceeded` |
| `tools`, `injection`, `role` | `trajectories`, each a `task` and its `result` |
| `review` | A [`ReviewResult`](code-review/outputs.md#reviewresult) |
| `demo` | `comparisons`, each with `task`, `answer`, `judge`, `attest` and `outcome` |
| `stats` | `rate`, `low`, `high`, `n` |
| `models` | `provider`, `source`, `models` |

A `report` holds one `result` per check, plus `overall_score` and `passed`. Every `result` has
the same fields: `check`, `passed`, `score`, `summary`, `findings`, `metadata` and
`prompt_version`. Each finding has `severity` (`pass`, `warn` or `fail`), `verdict`, `subject`,
`reason`, `evidence`, `step` and `metadata`.

From Python, `result.model_dump_json()` gives the same JSON as `data`.

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
