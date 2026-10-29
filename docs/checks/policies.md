# Policies

A policy is a set of your project's own rules. Attach it to an `Attest` instance once and it is
enforced on every run that instance evaluates.

```python
from attest import Attest, EvaluationPolicy, EvaluationRule

policy = EvaluationPolicy(
    name="customer-support",
    version="1.0",
    rules=[
        EvaluationRule(
            id="refund-check",
            description="Check eligibility before sending a refund.",
            kind="required_tool_order",
            values=["check_eligibility", "issue_refund"],
        ),
        EvaluationRule(
            id="no-guarantees",
            description="Do not guarantee a refund outcome.",
            kind="forbidden_text",
            values=["guaranteed"],
        ),
        EvaluationRule(
            id="tone",
            description="The answer must be respectful and concise.",
            kind="rubric",
            severity="warn",
        ),
    ],
)

judge = Attest(policy=policy)
report = judge.evaluate(run)      # the policy result is appended automatically
```

Load the same policy from a file:

```python
judge = Attest(policy="support-policy.yaml")
judge.policy_check(run)           # the policy only
```

## Rule kinds

| Kind | Checks | Needs a model? |
|---|---|---|
| `required_text` | The answer contains each value. | No |
| `forbidden_text` | The answer contains none of the values. | No |
| `required_tools` | Each listed tool was called. | No |
| `required_tool_order` | The listed tools were called in this order. | No |
| `allowed_tools` | No tool outside the list was called. | No |
| `evidence` | A claim is supported by the tool outputs. | Yes |
| `rubric` | The answer meets a written standard. | Yes |

`required_tools` and `required_tool_order` check that calls happened, not that they succeeded.
Add an `evidence` rule to check a tool's output. A policy made only of deterministic rules runs
offline.

Each rule's `severity` is `fail` (the default) or `warn`.

## Identity

Reports carry the policy's name, version and a stable SHA-256 hash in `report.metadata`, so a
score can always be traced to the exact rules that produced it. To skip a configured policy for
one call, pass it explicitly:

```python
judge.evaluate(run, enforce_policy=False)
```
