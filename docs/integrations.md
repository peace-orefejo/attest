---
description: "Use attest with LangChain, LangGraph, Haystack or any agent framework, and gate CI on pass rates with confidence intervals."
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

## Haystack

```python
from attest import Attest, from_haystack_messages
from haystack.dataclasses import ChatMessage

result = agent.run(messages=[ChatMessage.from_user(question)])
run = from_haystack_messages(result["messages"], allowed_tools=["search"])

report = Attest().evaluate(run)
```

The adapter pairs each tool call with the `ToolCallResult` that answers it and takes the last
assistant message as the final answer. It accepts `ChatMessage` objects or their `to_dict()`
form, so saved runs work too. A tool result marked as an error keeps its text as the output.

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
jq -e '.ok and .data.verdicts.block == 0' report.json
passed=$(jq '.data.verdicts.pass' report.json)
graded=$(jq '.data.evaluated' report.json)
attest stats "$passed" "$graded" | jq -e '.data.low >= 0.8'
```

`jq -e` exits non-zero when its result is `false`, so each line fails the step if its check
fails. The pass rate counts only runs whose verdict is `pass`; runs that need review don't
count as passing. Keep `report.json` as a
build artifact: every finding, with its evidence, is in it.

## AI code review pipelines

See [Code review mode](code-review/index.md).
