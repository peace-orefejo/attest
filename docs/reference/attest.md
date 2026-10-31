---
description: "API reference for the attest Python package: Attest, Trajectory, Report, CheckResult, Finding and every check."
---

# attest

The public API, importable as `from attest import ...`.

## Evaluator

::: attest.Attest

## Runs

::: attest.Trajectory

::: attest.Step

::: attest.ToolCall

::: attest.Artifact

## Results

::: attest.Report

::: attest.CheckResult

::: attest.Finding

::: attest.Severity

::: attest.VerdictPolicy

::: attest.ToolUsePolicy

## Checks

::: attest.evaluate

::: attest.judge_trajectory

::: attest.extract_claims

::: attest.verify_claims

::: attest.check_tool_use

::: attest.check_injection

::: attest.check_role_adherence

## Injection detectors

::: attest.RegexDetector

::: attest.RegexPattern

::: attest.load_regex_detector

## Policies

::: attest.EvaluationPolicy

::: attest.EvaluationRule

::: attest.load_policy

::: attest.check_policy

## Adapters

::: attest.from_langgraph_messages

## Statistics

::: attest.wilson_interval

::: attest.difference_is_real

::: attest.Proportion
