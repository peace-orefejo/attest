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

`error.code` is `invalid_input`, `missing_api_key`, `provider_config` or `command_failed`.
`provider_config` means the provider rejected the key (401), the key lacks permission (403) or
the model doesn't exist (404); the message never includes the key. `command_failed` means
an error the checks don't absorb stopped the command, such as a provider error during
`attest review`; `message` names the error.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The command ran. |
| `1` | A required API key is missing or rejected (`missing_api_key`, `provider_config`), or the command failed (`command_failed`). |
| `2` | The input or an option is invalid. |
| `3` | A budget stopped `attest run`. The runs graded so far are still printed. |

The exit code says whether the command ran, not whether the agent passed.

## What `data` holds

| Command | `data` |
|---|---|
| `run` | `trajectories`: one entry per graded run, each a `task` and its `report`. Then `total` (runs in the file), `evaluated` (runs graded), `verdicts` (how many runs got each verdict: `pass`, `review`, `block`), `passed` (runs whose checks all passed; this doesn't account for `review`, so gate on `verdicts`), `mean_overall_score`, `usage` (calls and tokens), and `budget_exceeded`: why a budget stopped the run, or `null`. |
| `tools`, `injection`, `role` | `trajectories`: one entry per run, each a `task` and its `result` |
| `review` | A [`ReviewResult`](code-review/outputs.md#reviewresult) |
| `demo` | `comparisons`: one per run, with `task`, `answer`, the plain LLM judge's verdict (`judge`), attest's faithfulness result (`attest`), and `outcome`: `caught` (attest caught a false claim the judge passed), `both_caught`, `both_passed` or `judge_only` |
| `stats` | `rate`, `low`, `high`, `n` |
| `models` | `provider`, `source` (`live` or `curated`), `models` |

A `report` holds `results` (one per check), `overall_score`, `passed`, `verdict` (`pass`,
`review` or `block`), `blocking` (the findings that blocked, each a `check`, `verdict` and
`subject`), `scores` (each check's score by name) and `claim_coverage` (the share of claims
faithfulness checked, or `null`). Each result and finding has the fields
described in [How it works](concepts.md#results-and-findings); a finding in a report also has
its `disposition`. See [Reports](concepts.md#reports). Gate on `verdict`: `passed` only says
every check passed, so an inconclusive run can have `passed: true` and `verdict: "review"`.

From Python, `report.model_dump_json()` gives the same JSON as one `report` in `attest run`'s
output, and a check's `result.model_dump_json()` the same as one `result` from `attest tools`,
`injection` or `role`.

## Examples

```bash
# The failed claims, with the evidence against them
attest run run.json | jq '.data.trajectories[].report.results[].findings[]
  | select(.severity == "fail") | {subject, reason, evidence}'

# Fail a CI step unless every run's verdict is pass (review and block both fail it)
attest run runs.jsonl | jq -e '.ok and .data.verdicts.pass == .data.total'

# Fail only on blocks, and let runs that need review through
attest run runs.jsonl | jq -e '.ok and .data.verdicts.block == 0'
```

## Schemas

`attest schema <command>` prints the JSON Schema for a command's output. The same schemas are
published as `schemas/v1/<command>.json` on this site, for example
[run.json](schemas/v1/run.json) and [error.json](schemas/v1/error.json).

Within `schema_version` `"1"`, fields may be added but never removed or redefined.
