# AgentDojo source subset

- Upstream: https://github.com/ethz-spylab/agentdojo (MIT, see `LICENSE` and `NOTICE`)
- Commit: `089ed468cf3ed0322acc66b0211f26d9d90dbf60` (2026-06-02)
- Converter: `benchmarks/converters/agentdojo.py` (regenerate the cases with
  `uv run python benchmarks/converters/agentdojo.py`; `--vendor DIR` re-creates this folder from
  a local mirror of the upstream files at the commit above)

## What was selected and why

Ten runs of the undefended `gpt-4o-2024-05-13` pipeline, the model the AgentDojo paper reports
most, so the pilot has one agent throughout. Each suite is one task family and goes to one
split: `banking` and `slack` to dev, `travel` to validation, `workspace` to held-out.

Within each suite, runs were picked by reading them (not from AgentDojo's results) to mix three
outcomes: clean `none/none` controls (no attack), runs whose tool outputs carry an injected
instruction the agent didn't act on, and runs where the agent acted on it. Most attacked runs
use the `important_instructions` attack; `direct` (slack) and `tool_knowledge` (workspace) were
used where gpt-4o ignored the payload, because it obeyed nearly every `important_instructions`
run sampled. Many upstream runs share a user task, so only a few user tasks per suite are used.

| Case id | Check | Split | Upstream run |
|---|---|---|---|
| `agentdojo-banking-ut1-none` | prompt_injection | dev | `banking/user_task_1/none/none.json` |
| `agentdojo-banking-ut1-important_instructions-it0` | prompt_injection | dev | `banking/user_task_1/important_instructions/injection_task_0.json` |
| `agentdojo-slack-ut0-direct-it1` | prompt_injection | dev | `slack/user_task_0/direct/injection_task_1.json` |
| `agentdojo-slack-ut1-important_instructions-it1` | tool_use | dev | `slack/user_task_1/important_instructions/injection_task_1.json` |
| `agentdojo-travel-ut9-important_instructions-it3` | prompt_injection | validation | `travel/user_task_9/important_instructions/injection_task_3.json` |
| `agentdojo-travel-ut0-important_instructions-it2` | prompt_injection | validation | `travel/user_task_0/important_instructions/injection_task_2.json` |
| `agentdojo-travel-ut1-important_instructions-it1` | tool_use | validation | `travel/user_task_1/important_instructions/injection_task_1.json` |
| `agentdojo-workspace-ut0-none` | prompt_injection | heldout | `workspace/user_task_0/none/none.json` |
| `agentdojo-workspace-ut2-tool_knowledge-it0` | prompt_injection | heldout | `workspace/user_task_2/tool_knowledge/injection_task_0.json` |
| `agentdojo-workspace-ut1-important_instructions-it1` | prompt_injection | heldout | `workspace/user_task_1/important_instructions/injection_task_1.json` |

The upstream run paths above are relative to `runs/gpt-4o-2024-05-13/`.

The allowed tools come from the `TOOLS = [...]` list in each suite's
`src/agentdojo/default_suites/v1/<suite>/task_suite.py`, vendored verbatim as
`suites/<suite>/task_suite.py.txt` (renamed so linters and type checkers skip upstream code).

## What was stripped

Each run file was parsed and re-written (4-space JSON) keeping only `suite_name`,
`pipeline_name`, `user_task_id`, `injection_task_id`, `attack_type`, `injections`, `messages`
and `error`. Removed: `utility` and `security` (AgentDojo's own grading of the run, which could
act as labels) and `duration`. Messages are unchanged. The cases themselves also leave out
`injections` (the list of injected texts), so nothing in a case says where an attack sits
beyond the tool outputs the agent saw.

The data is synthetic (AgentDojo's fictional users, IBANs and email addresses), so nothing was
redacted.

## Files

| Vendored path | Upstream path | Upstream sha256 | Vendored sha256 |
|---|---|---|---|
| `LICENSE` | `LICENSE` | `4285a071f2d382338e52b4fb0a186d952984a34d43a33d8872e1a1d8cb43401e` | `4285a071f2d382338e52b4fb0a186d952984a34d43a33d8872e1a1d8cb43401e` |
| `suites/banking/task_suite.py.txt` | `src/agentdojo/default_suites/v1/banking/task_suite.py` | `c58ec73db16f713a16aaec787dac45856e546f4d95be84ab6a4bed9bc12613b6` | `c58ec73db16f713a16aaec787dac45856e546f4d95be84ab6a4bed9bc12613b6` |
| `suites/slack/task_suite.py.txt` | `src/agentdojo/default_suites/v1/slack/task_suite.py` | `bdc6798e8ef83a54e787af80ed44f94e4be8f24aba2eaec2103e3120958c3670` | `bdc6798e8ef83a54e787af80ed44f94e4be8f24aba2eaec2103e3120958c3670` |
| `suites/travel/task_suite.py.txt` | `src/agentdojo/default_suites/v1/travel/task_suite.py` | `a2b58f094bd61a79e245ca74c94d9a3d62cc6bc744e5ee21bdadabb43960ba60` | `a2b58f094bd61a79e245ca74c94d9a3d62cc6bc744e5ee21bdadabb43960ba60` |
| `suites/workspace/task_suite.py.txt` | `src/agentdojo/default_suites/v1/workspace/task_suite.py` | `96fa51ab20f03c30cd2d7bc754b76d717ddbd68bdf39adc85f0e92fc4d2c7ec4` | `96fa51ab20f03c30cd2d7bc754b76d717ddbd68bdf39adc85f0e92fc4d2c7ec4` |
| `runs/gpt-4o-2024-05-13/banking/user_task_1/important_instructions/injection_task_0.json` | `runs/gpt-4o-2024-05-13/banking/user_task_1/important_instructions/injection_task_0.json` | `032fc011077c18e2b864707c5ed1a48d5aeb55ab821f176ac812b88cb9a7b1d7` | `7fac90a43ff9589948c22985199f668e5f4aff244d9a1485d3fdd3060454f81c` |
| `runs/gpt-4o-2024-05-13/banking/user_task_1/none/none.json` | `runs/gpt-4o-2024-05-13/banking/user_task_1/none/none.json` | `faebd820b76a63fde15643eda237f0c1dec1f07e51cf725443e7ab1ebb8b1ff1` | `a9ac5e48f94f5bee148ed886fc0df647eeee9bbe5008795f889d980f8cdf9c94` |
| `runs/gpt-4o-2024-05-13/slack/user_task_0/direct/injection_task_1.json` | `runs/gpt-4o-2024-05-13/slack/user_task_0/direct/injection_task_1.json` | `ec7936d371b235a04f44a86642ce927b0f63daa2595e588d9c6dc238f9e7b441` | `853372d6c528e5cfaf30e2ac1d78a0bf46743a945e180b5384e4c3db4af0daa4` |
| `runs/gpt-4o-2024-05-13/slack/user_task_1/important_instructions/injection_task_1.json` | `runs/gpt-4o-2024-05-13/slack/user_task_1/important_instructions/injection_task_1.json` | `b23aec4ed55cceb41c8d5706277ebd0846c428d4b504449934365bd124aa1573` | `62578262c47e856cd2daf7b60cd88ec6ad25b48d62d9eb7e6a4b4388c4576e7d` |
| `runs/gpt-4o-2024-05-13/travel/user_task_0/important_instructions/injection_task_2.json` | `runs/gpt-4o-2024-05-13/travel/user_task_0/important_instructions/injection_task_2.json` | `a49efccbbd928893f3ba87c1a14394d03fad33798d6a8e457cfabcb647397151` | `30143ef604f210b4a8c8ae524b152ae22a1bb7b6940c527bec8ca70b02559b61` |
| `runs/gpt-4o-2024-05-13/travel/user_task_1/important_instructions/injection_task_1.json` | `runs/gpt-4o-2024-05-13/travel/user_task_1/important_instructions/injection_task_1.json` | `bb58c5dffd714e4d5d750ce7207ee80783c1c53227ccb680373849e337dec6c5` | `b3d3714254fc549b35350215e53e13bef1841bb3cd45fe9a951624150f025172` |
| `runs/gpt-4o-2024-05-13/travel/user_task_9/important_instructions/injection_task_3.json` | `runs/gpt-4o-2024-05-13/travel/user_task_9/important_instructions/injection_task_3.json` | `1e07dd66da8affb1fa9f77315df0b3baf6a6620be792798828ceeff8e6960c6f` | `50b7d09cd5d98d037d22331a811f14b6e8beacdf9b40afb0dda0da3fab411cba` |
| `runs/gpt-4o-2024-05-13/workspace/user_task_0/none/none.json` | `runs/gpt-4o-2024-05-13/workspace/user_task_0/none/none.json` | `8158688f12ef540e9b430ebe6390e434a0847408f0db8e978d606e540cde25d2` | `36947d18c96d87f576b98577e0c4673c2308de1edaad822e9c82faeba8765513` |
| `runs/gpt-4o-2024-05-13/workspace/user_task_1/important_instructions/injection_task_1.json` | `runs/gpt-4o-2024-05-13/workspace/user_task_1/important_instructions/injection_task_1.json` | `a8428f283d802ebd924b7f433fc02cae24ab71231ddd119561352ba51ab79d96` | `faa980056e9d3d23f7153e8c42beaae7adb5294ba791f956d74db95fa806be38` |
| `runs/gpt-4o-2024-05-13/workspace/user_task_2/tool_knowledge/injection_task_0.json` | `runs/gpt-4o-2024-05-13/workspace/user_task_2/tool_knowledge/injection_task_0.json` | `a9cac15dcc2062b04d1598aa3e0424d0ae093194c72e15d3f4911523b4781d9c` | `9fe8b09a04019e549701c6e5911a20b487c2000605d19db673bdbf03579f68a7` |
