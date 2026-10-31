---
description: "What attest assumes, what it can't establish, and how to use its results safely: evidence authenticity, heuristics, unmeasured accuracy."
---

# Limitations

attest evaluates a recorded run against the evidence in that record. It is an evaluation
toolkit, not a guarantee: its own accuracy hasn't been measured on a labelled benchmark yet, and
several of its checks rest on assumptions you should know before you rely on a result.

## What attest assumes

| Assumption | If it doesn't hold |
|---|---|
| The run is authentic: each tool output really came from that tool, unmodified. | attest grades against fabricated evidence as if it were real. A faked "refund approved" output backs a faked claim. |
| The run is complete: every tool call the agent made is recorded. | A claim that rests on a missing call comes back `unverifiable`, and an unrecorded harmful call goes unseen. |
| The agent received exactly the recorded output. | attest can't tell whether the agent saw something different. |

attest checks claims against evidence; it doesn't establish where the evidence came from.
Authenticating runs (signed tool outputs, tamper-evident logs, provenance that ties a result to
an execution) is outside what attest does today.

## Where the checks rely on heuristics

- **Tool errors** are detected from the output text (empty, or starting with error, exception
  or traceback) unless the run sets `ToolCall.is_error`. A structured failure such as an HTTP
  500 body, or a tool that legitimately returns nothing, can be misread. Set `is_error` when you
  know the status.
- **Retries** are matched by tool name. Two `charge_card` calls count as a retry even if they
  were different transactions.
- **Tool use** checks that a tool was allowed and its errors were handled. It doesn't check that
  the arguments were valid. Whether it was the right tool is checked only with `--appropriate`.
- **Injection detection** is pattern-based first. It can flag harmless text that looks like an
  instruction and miss payloads it has no pattern for.
- **Judgment checks** (faithfulness, role, deep injection, the tool-error answer question) ask a
  language model. Its mistakes are constrained, not removed: it sees only the claim and the
  evidence, but it can still misjudge them.

## What the numbers mean

- A Wilson interval from `attest stats` describes how noisy a pass rate is. It says nothing about
  whether attest graded each run correctly.
- An inconclusive faithfulness result (claims that couldn't be checked) is `review`, not `pass`,
  by default. A `pass` means attest found nothing wrong in what it could check, not that
  everything was checked; `metadata["claims_checked"]` and `claims_total` say how much was.

## Using results safely

- Gate on `verdict`, and treat `review` as "a person should look", not as a pass.
- Record tool status (`is_error`) and every tool call, and keep the run unmodified between the
  agent and attest.
- Compare models and prompt versions on your own labelled runs before trusting a change.
- Don't treat attest's output as a security guarantee or an audit record.
