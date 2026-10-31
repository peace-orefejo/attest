---
description: "Use attest with LangChain, LangGraph or any agent framework, and gate CI on pass rates with confidence intervals."
---

# Integrations

attest grades a `Trajectory`, so it works with any framework once you convert the agent's
history into one.

## LangGraph

```python
from attest import Attest, from_langgraph_messages

result = graph.invoke({"messages": [("user", question)]})
run = from_langgraph_messages(result["messages"], task=question)

report = Attest().evaluate(run)
```

The adapter pairs each tool call with its `ToolMessage` output and takes the last AI message as
the final answer. It works on any list of LangChain messages, so LangChain agents that return
their message history work too.

## Anything else

Build the run from your own logs:

```python
from attest import Step, ToolCall, Trajectory

run = Trajectory(
    task=question,
    allowed_tools=["search", "fetch"],
    steps=[
        Step(tool_call=ToolCall(name="search", arguments={"q": question}, output=search_text)),
        Step(tool_call=ToolCall(name="fetch", arguments={"url": url}, output=page_text)),
    ],
    final_answer=answer,
)
```

Record each tool's output exactly as the agent received it. attest can only check claims against
the evidence the run contains. `examples/quickstart.py` is a complete, runnable example.

## In CI

Run attest over a JSONL file of recorded runs, then gate on the pass rate's confidence interval
rather than on a single run, so one noisy run can't fail the build:

```bash
set -e
attest run evals/runs.jsonl > report.json   # exits non-zero on a missing key, bad input or budget stop
jq -e '.ok' report.json
passed=$(jq '.data.passed' report.json)
graded=$(jq '.data.evaluated' report.json)
attest stats "$passed" "$graded" | jq -e '.data.low >= 0.8'
```

`jq -e` exits non-zero when its result is `false`, so each line fails the step if its check
fails. Keep `report.json` as a
build artifact: every finding, with its evidence, is in it.

## AI code review pipelines

See [Code review mode](code-review/index.md).
