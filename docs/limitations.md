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

## Failures and bad input

No failure and no missing input turns into a `pass`.

| What happens | Result |
|---|---|
| A budget runs out (`BudgetExceeded`) | Raised. `attest run` stops, prints the runs graded so far and exits 3. |
| The provider rejects the key (401), the key lacks permission (403) or the model doesn't exist (404) | `ProviderConfigError` is raised and every check stops: it's a setup mistake, not an inconclusive evaluation. The CLI prints a `provider_config` error and exits 1. The message never includes the key or the provider's response. |
| A rate limit, timeout or server error (408, 409, 429, 5xx) | Retried up to three attempts in all; if it keeps failing, the affected findings are inconclusive (`review`). |
| Claim extraction or verification fails, or a verifier skips a claim | Those claims are `unverifiable` with `metadata["checked"]` false and the error in `reason`. Verdict `review`. |
| The role, deep injection, tool-choice or policy (`evidence`, `rubric`) model call fails | An `unchecked` finding with the error. Verdict `review`. |
| The tool-error answer question fails | The error's `recovery` is `unchecked`, so the call is `error_silent`. Verdict `review`. |
| A code review injection confirmation fails | The hit stays unconfirmed and coverage is incomplete, so the scan is never `clean`. |
| A code review guideline check or writer call fails | Raised. The CLI prints a `command_failed` error and exits 1. |
| No steps | Claims have no evidence, so they're `unverifiable` (`review`). Tool use and injection have nothing to flag. |
| An empty final answer, or one with no claims | Faithfulness has nothing to check and passes. Unrecovered tool errors are still checked. |
| No system prompt | Role is `unchecked` (`review`), with no model call. |
| `allowed_tools` is `null` / `[]` | Every tool is allowed / no tool is allowed. |
| A tool call with no output | Counted as a tool error. |
| A very long output, or an artifact that can't be read | Injection reports `unscanned_content`; faithfulness shows the artifact as incomplete and lists it in `metadata`. |
| Control characters, markup or odd arguments | Treated as data: escaped in prompts and printed as valid JSON. |
| A file that isn't valid UTF-8 or valid JSON | The CLI prints an `invalid_input` error and exits 2. |

A malformed or empty model response is retried twice, then fails like any other call. In
`evaluate()`, a failed call never stops the other checks: only the affected findings are
inconclusive. The exceptions are a budget stop and a provider configuration error, which stop
the evaluation.

`unscanned_content` follows `VerdictPolicy(on_injection_warning=...)`, which is `pass` by
default; set it to `review` to gate on full scan coverage.

## Using results safely

- Gate on `verdict`, and treat `review` as "a person should look", not as a pass.
- Record tool status (`is_error`) and every tool call, and keep the run unmodified between the
  agent and attest.
- Compare models and prompt versions on your own labelled runs before trusting a change.
- Don't treat attest's output as a security guarantee or an audit record.
