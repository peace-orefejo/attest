---
description: "Enforce your project's own rules on every AI agent run: required and forbidden text, tool order, allowed tools and rubric checks."
---

# Policies

**Question:** did the run follow your project's own rules?

A policy is a list of rules for your project, such as "check eligibility before issuing a
refund" or "never promise a refund". Attach it to an `Attest` grader once, and every run that
grader evaluates is checked against it. The result is a `policy` check in the report.

Policies are set in Python. The command line doesn't take a policy.

## Rule kinds

| Kind | Checks | Needs a model? |
|---|---|---|
| `required_text` | The answer contains each value. | No |
| `forbidden_text` | The answer contains none of the values. | No |
| `required_tools` | Each listed tool was called. | No |
| `required_tool_order` | The listed tools were called in this order. | No |
| `allowed_tools` | No tool outside the list was called. | No |
| `evidence` | The tool outputs support the claim in `description`. | Yes |
| `rubric` | The answer meets the standard in `description`. | Yes |

If the model fails on an `evidence` or `rubric` rule, that rule is `unchecked`, a warning with
the error in `reason`, and the verdict is `review`.

`required_tools` and `required_tool_order` check that calls happened, not that they succeeded.
Add an `evidence` rule to check what a tool returned. A policy with no `evidence` or `rubric`
rules runs offline.

## Rule fields

| Field | Meaning |
|---|---|
| `id` | A short, unique name, shown in findings. |
| `description` | What the rule requires. For `evidence` and `rubric` rules, this is what the grading model checks. |
| `kind` | One of the kinds above. Defaults to `rubric`. |
| `values` | The text or tool names that text and tool rules check. |
| `severity` | `fail` (the default) fails the check; `warn` only reports. |
| `case_sensitive` | For text rules. Defaults to `false`. |

## Example

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

grader = Attest(policy=policy)
report = grader.evaluate(run)     # includes a "policy" result
grader.policy_check(run)          # the policy result on its own
```

The same policy can live in a YAML or JSON file with the same fields:

```yaml
name: customer-support
version: "1.0"
rules:
  - id: refund-check
    description: Check eligibility before sending a refund.
    kind: required_tool_order
    values: [check_eligibility, issue_refund]
```

```python
grader = Attest(policy="support-policy.yaml")
```

## Skipping the policy

To evaluate one run without the policy, pass `enforce_policy=False`:

```python
grader.evaluate(run, enforce_policy=False)
```

Every report records the policy's name, version and a hash of its rules in `report.metadata`,
so a score can always be traced to the exact rules that produced it.
