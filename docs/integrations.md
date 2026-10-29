# Integrations

attest grades a `Trajectory`, so it works with any framework once you convert the agent's
history into one.

## LangChain and LangGraph

```python
from attest import Attest, from_langgraph_messages

result = graph.invoke({"messages": [("user", question)]})
run = from_langgraph_messages(result["messages"], task=question)

report = Attest().evaluate(run)
```

The adapter pairs each tool call with its `ToolMessage` output and takes the last AI message as
the final answer.

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

Run attest over a JSONL file of recorded runs and fail the build when a check fails:

```bash
attest run evals/runs.jsonl --json > report.json
```

Gate on pass rates with their confidence intervals, not on a single run, so one noisy run can't
fail the build.

## AI code review pipelines

See [Code review mode](code-review/index.md).
