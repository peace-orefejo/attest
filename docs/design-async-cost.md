# Design: async batch evaluation and cost guardrails (v0.8)

Status: **proposal** — not yet implemented. This is the plan for the one weakness we deliberately
did **not** rush into 0.7.x, because it touches `_llm` and the public API and deserves review.

## Problem

`attest` is entirely synchronous. Every judge call blocks; `vote()` fires its N samples one after
another; and evaluating a list of trajectories is a sequential loop. There are also no cost
controls — nothing bounds how many tokens or calls an evaluation run spends.

For a single trajectory this is fine (a full evaluate is roughly: faithfulness = 2 calls, plus one
`vote` of 3 for each of role / tool_use / deep-injection / semantic-policy rule). The pain is at
**batch scale**: evaluating 500 trajectories serially, each making a handful of round-trips, is
dominated by network latency that concurrency would erase, and there is no budget to stop a
runaway or unexpectedly expensive run.

Result caching (shipped in 0.7.x via `Attest(cache=True)`) already removes repeated work on
*identical* prompts. What remains is concurrency and spend control.

## Goals

1. **Concurrency** — overlap independent LLM calls: across trajectories in a batch, and across the
   independent samples within a `vote`.
2. **Cost guardrails** — a per-run token/call budget that fails closed with a clear error, plus an
   accounting of what a run spent.
3. **No breaking changes** — the current sync API keeps working unchanged; async and batching are
   additive.

## Non-goals

- Streaming responses. Judges return small structured objects; streaming buys nothing.
- A distributed job queue. In-process concurrency (asyncio) is the right scope.
- Changing any judging *logic* — same prompts, same self-consistency, same verdicts.

## Design

### 1. An async LLM chokepoint

`_llm.call` / `vote` stay as the sync surface, implemented on top of new async primitives:

```python
async def acall(*, system, user, output, sample=0, ...) -> T: ...
async def avote(*, system, user, output, key, samples=3, ...) -> T:
    results = await asyncio.gather(*(
        acall(system=system, user=user, output=output, sample=i) for i in range(samples)
    ))
    ...
def call(**kw):  return _run_sync(acall(**kw))
def vote(**kw):  return _run_sync(avote(**kw))
```

- Uses instructor's async client (`AsyncInstructor` / `from_provider(..., async_client=True)`).
- The response cache (`using_cache`) and the sample-indexed key carry over unchanged; a cache hit
  short-circuits before the await.
- `_run_sync` runs the coroutine on a private event loop when called from sync code, so existing
  callers are untouched.

### 2. Concurrent batch evaluation

Add a batch entry point that overlaps trajectories with a bounded semaphore:

```python
class Attest:
    async def aevaluate(self, traj, **kw) -> Report: ...
    async def aevaluate_many(self, trajs, *, concurrency=8, **kw) -> list[Report]:
        sem = asyncio.Semaphore(concurrency)
        async def one(t):
            async with sem:
                return await self.aevaluate(t, **kw)
        return await asyncio.gather(*(one(t) for t in trajs))

    def evaluate_many(self, trajs, *, concurrency=8, **kw) -> list[Report]:
        return _run_sync(self.aevaluate_many(trajs, concurrency=concurrency, **kw))
```

`concurrency` caps in-flight requests to stay within provider rate limits. A shared response cache
across the batch (the instance `_cache`) means trajectories with overlapping evidence dedupe for
free.

### 3. Cost guardrails

A budget object threaded through the run via a `ContextVar`, updated from each response's usage:

```python
@dataclass
class Budget:
    max_calls: int | None = None
    max_tokens: int | None = None
    def spend(self, *, calls: int, tokens: int) -> None: ...   # raises BudgetExceeded when over

class BudgetExceeded(RuntimeError): ...
```

- `Attest(budget=Budget(max_tokens=2_000_000))` (or `max_calls=`) sets the ceiling for a run.
- Instructor exposes token usage on the raw completion; `acall` records `(1 call, prompt+completion
  tokens)` after each response and calls `budget.spend(...)`.
- Exceeding the budget raises `BudgetExceeded` — the run fails closed rather than silently spending.
- `Report.metadata["cost"] = {"calls": N, "tokens": M}` so every run reports what it spent, budget
  or not.

### 4. Surfacing it

- New public exports: `Budget`, `BudgetExceeded`, `Attest.evaluate_many` / `aevaluate` /
  `aevaluate_many`.
- CLI: `attest run --concurrency 16 --max-tokens 5_000_000 runs.jsonl`, and cost printed in the
  summary / included in `--json`.

## Risks and mitigations

- **Provider rate limits** — the `concurrency` semaphore plus existing retry-on-empty handling; a
  429 backoff is a small addition to `acall`.
- **Event-loop reentrancy** — `_run_sync` must detect an already-running loop (e.g. inside a
  notebook) and use it rather than creating a nested one.
- **Token accounting drift** — usage fields differ per provider; normalize in one place
  (`providers.py`) and treat a missing count as `0` with a one-time warning, never a crash.
- **Self-consistency** — `avote` must still issue N *independent* samples; the sample-indexed cache
  key already guarantees they are distinct within a run and reused across runs.

## Rollout

1. Async primitives in `_llm` (`acall`/`avote`) with `call`/`vote` delegating; no API change.
2. `Budget` + accounting; opt-in via `Attest(budget=...)`; `cost` in `Report.metadata`.
3. `aevaluate` / `evaluate_many` with bounded concurrency.
4. CLI flags and docs.

Each step is independently shippable and testable (async paths mocked with a fake `AsyncInstructor`,
the same way the sync tests mock `call`).
