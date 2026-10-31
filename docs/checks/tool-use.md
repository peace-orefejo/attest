---
description: "The tool-use check flags calls to tools an agent wasn't allowed to use and tool errors it didn't recover from or report. Offline unless you ask it to read the final answer."
---

# Tool use

**Question:** did the agent call tools it's allowed to use, and recover from their errors or
tell the user about them?

The allowed-tool and retry checks are deterministic and need no API key. Reading the final
answer for an unrecovered error takes one model call per error.

```bash
attest tools run.json
```

Each tool call becomes a finding with the tool's name in `subject` and the step index in `step`:

```json
{
  "severity": "pass",
  "verdict": "correct",
  "subject": "charge_card",
  "reason": "The tool returned an error; a retry at step 2 worked.",
  "evidence": null,
  "step": 0,
  "metadata": {"allowed": true, "recovery": "retried", "recovered_at": 2, "appropriate": null}
}
```

In `metadata`:

- `recovery` says how the agent dealt with an error (see [Errors](#errors)). It's `null` when
  the tool didn't return an error.
- `recovered_at` is the step of the call that recovered the error, or `null`.
- `appropriate` is `null` unless you asked for the [tool-choice check](#tool-choice).

```python
grader.tool_use(run)
```

## Rules

Each tool call gets one verdict, checked in this order:

| Verdict | Severity | When |
|---|---|---|
| `disallowed_tool` | fail | The tool isn't in `allowed_tools`. If the run has no `allowed_tools` (`null`), every tool is allowed; an empty list allows none. |
| `error_claimed_success` | fail | The tool errored, nothing recovered it, and the final answer says it succeeded. |
| `error_silent` | fail | The tool errored, nothing recovered it, and the final answer doesn't mention it, or no model was available to check (`recovery` is `unchecked`). |
| `incorrect` | fail | The [tool-choice check](#tool-choice) found the tool a poor choice. |
| `unchecked` | warn | The tool-choice model call failed, so the choice wasn't checked. The verdict is `review`. |
| `correct` | pass | Anything else. |

The check fails when any call fails. The score is the share of correct calls. The summary lists
the call sequence and every problem with its step number.

## Errors

A tool call is an error when its output is empty or looks like one: it starts with "error",
"exception" or "traceback", or contains "error:" or "exception:". Set `is_error` on the
`tool_call` to decide this yourself:

```json
{"name": "charge_card", "arguments": {"order": 42}, "output": "status 402", "is_error": true}
```

Each error gets a `recovery`:

| `recovery` | Meaning |
|---|---|
| `retried` | A later call to the same tool didn't error. |
| `fallback` | A later call to one of the tool's `tool_fallbacks` didn't error. |
| `acknowledged` | Nothing recovered it, and the final answer tells the user it failed. |
| `silent` | Nothing recovered it, and the final answer doesn't mention it. |
| `claimed_success` | Nothing recovered it, but the final answer says it succeeded. |
| `unchecked` | Nothing recovered it, and no model was available to read the final answer. |

A call to some other tool never recovers an error. attest doesn't guess which tools are
equivalent, so declare them on the run:

```json
{"tool_fallbacks": {"charge_card": ["charge_card_backup"]}}
```

For an error nothing recovered, one model call asks whether the final answer says the
operation failed, says it succeeded, or doesn't mention it. The model sees only the tool name,
the error output and the final answer. The call runs when a model is available:

- `attest tools --appropriate` or `attest tools --check-answer`.
- `grader.tool_use(run, appropriate=True)` or `grader.tool_use(run, check_answer=True)`.
- `attest run` and `grader.evaluate(run)` whenever an API key is set.
- `check_tool_use(run)` inside `with attest.llm.using(client):`.

Without one, attest stays offline and reports the error as `unchecked`, which fails the call.
If the model call itself fails, the error is also `unchecked`, with the reason.

```bash
attest tools run.json --check-answer
```

## Tool choice

`--appropriate` (or `appropriate=True`) adds one model call per tool call. It asks whether the
tool was a reasonable choice for the step, given the task and the tool descriptions in the
system prompt. It judges the choice of tool only, not whether the answer was good.

```bash
attest tools run.json --appropriate
```
