# Tool use

**Question:** did the agent call tools it's allowed to use, and deal with their errors?

This check is deterministic and needs no API key.

```bash
attest tools run.json
```

Each tool call becomes a finding with the tool's name in `subject` and the step index in `step`:

```json
{
  "severity": "pass",
  "verdict": "correct",
  "subject": "web_search",
  "reason": "Allowed tool; no unhandled error.",
  "evidence": null,
  "step": 0,
  "metadata": {"allowed": true, "error_handled": null, "appropriate": null}
}
```

```python
judge.tool_use(run)
```

## Rules

Each tool call is `correct` or `incorrect`:

- **Not allowed.** The tool isn't in `allowed_tools`. If the run has no `allowed_tools`, every
  tool is allowed.
- **Unhandled error.** The output looks like an error and no later step did anything about it.

The score is the share of correct calls. The summary lists the call sequence and every problem
with its step number.

## Tool choice

`--appropriate` (or `appropriate=True`) adds one model call per tool call. It asks whether the
tool was a reasonable choice for the step, given the task and the tool descriptions in the
system prompt. It judges the choice of tool only, not whether the answer was good.

```bash
attest tools run.json --appropriate
```
