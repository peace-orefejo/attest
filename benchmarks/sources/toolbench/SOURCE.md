# ToolBench source

- Upstream: https://github.com/OpenBMB/ToolBench
- Commit: `d56fdd89faf8c91fa135090b212bb9057ee5cfc2`
- Licence: Apache License 2.0 (`LICENSE`, copied verbatim; credit in `NOTICE`). The README says
  the data "is distributed under Apache License 2.0".
- Converter: `benchmarks/converters/toolbench.py` (cases and draft labels in
  `toolbench_cases.py`, redaction in `toolbench_redact.py`). Regenerate with
  `uv run python benchmarks/converters/toolbench.py`.

## Vendored files

Fetched from the commit above, at the same path, by `uv run python
benchmarks/converters/toolbench.py --vendor` (`toolbench_vendor.py`), which checks each file
against its upstream sha256 before writing it. `LICENSE` is copied verbatim. Each JSON sample
is redacted (see [Redactions](#redactions)) and otherwise kept as upstream published it: the
same fields, two-space indent, ASCII escapes and line endings (CRLF in the G1 files), so a diff
against upstream shows only the redacted spans. Only the in-repo samples are used; the full
`data.zip` (Google Drive) is not.

| Path | Upstream sha256 (at the commit) | Vendored sha256 (after redaction) |
|---|---|---|
| `data_example/answer/G1_answer/10_ChatGPT_DFS_woFilter_w2.json` | `76a77721640045e07142c669008611e6b82b25007c73427aec771adbf9dd9841` | `baf7733cc5f1822914ebf9801484f32521f518518106c145606cffda625a2fb0` |
| `data_example/answer/G1_answer/11_ChatGPT_DFS_woFilter_w2.json` | `3f935fe99b99beccb727763e8407ab9fdb5f2cf45d85d998327b669ab2ea52ab` | `d4077d5622af803603e6571dac904d74f917ed7d9cbd0dfe43b588c2010a006a` |
| `data_example/answer/G1_answer/57_ChatGPT_DFS_woFilter_w2.json` | `8279c9999dad881db8bc9e112feeb51ca2861e89d835111408f218af297af531` | `8279c9999dad881db8bc9e112feeb51ca2861e89d835111408f218af297af531` |
| `data_example/answer/G1_answer/59_ChatGPT_DFS_woFilter_w2.json` | `8fea509e1be896331fdfd587ab4668281ee820f89cdb9a1760c218ed7804c2be` | `8fea509e1be896331fdfd587ab4668281ee820f89cdb9a1760c218ed7804c2be` |
| `data_example/answer/G2_answer/52_ChatGPT_DFS_woFilter_w2.json` | `c6c2da0b425e0122838b1e15be199492686b2b10b1d60605d6a52523c214bdcb` | `c6c2da0b425e0122838b1e15be199492686b2b10b1d60605d6a52523c214bdcb` |
| `data_example/answer/G2_answer/127_ChatGPT_DFS_woFilter_w2.json` | `a32cc5c8947b2db443fd0c6c9a3b12905624c15a460ec7e9d4fa18df345675e8` | `a32cc5c8947b2db443fd0c6c9a3b12905624c15a460ec7e9d4fa18df345675e8` |
| `data_example/answer/G3_answer/21_ChatGPT_DFS_woFilter_w2.json` | `5f99a71cae2979600262f7b6b9b475399530496b56f475b03727b27b0cdfb176` | `5f99a71cae2979600262f7b6b9b475399530496b56f475b03727b27b0cdfb176` |
| `data_example/answer/G3_answer/3_ChatGPT_DFS_woFilter_w2.json` | `fdf868ff795bc0c9a153f4d492f40eb889caa2f60cad931bca6209c2e11dc263` | `fdf868ff795bc0c9a153f4d492f40eb889caa2f60cad931bca6209c2e11dc263` |
| `LICENSE` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |

Only G1 10 and G1 11 change; the other files had nothing to redact, so their two digests are
equal. Total vendored: about 510 KB.

## What was selected and why

Upstream ships 15 answer samples (5 per group). Each is a DFSDT search over one query, made by
ChatGPT. The group sets the split, so a tool never appears in two splits:

| Group | Split | `task_family` | Used | Not used |
|---|---|---|---|---|
| G1 (single tool) | `dev` | `toolbench/g1` | 10, 11, 57, 59 | 69: no `train_messages` (only the raw tree) and marked invalid upstream |
| G2 (intra-category multi-tool) | `validation` | `toolbench/g2` | 52, 127 | 102: offers the `transitaires` tool, which G1 uses; 10, 119: give up like 127, kept one |
| G3 (intra-collection multi-tool) | `heldout` | `toolbench/g3` | 21, 3 | 13: gives up; 8: no `train_messages`; 15: about 190 KB, and its only data-bearing call is marked as an error upstream although it returned results, which makes the tool-use labels unreliable |

The RapidAPI tools offered (the suffix after `_for_` in each function name) are disjoint across
the three splits; `toolbench_test.py` checks this.

**Which chain.** An answer is a search tree, and `answer_generation.train_messages` holds one
message chain per expansion step, each a prefix of the next. The converter takes the **last
chain** in `train_messages` (the full final path) and requires it to end with a call to `Finish`.
Every used sample's last chain is the path that reached the final `Finish`; `origin_ref` names
its index.

## Mapping

- `system_prompt`: the chain's system message (ToolBench's generic AutoGPT prompt with the
  tool descriptions).
- `task`: the first user message, without the trailing `Begin!`.
- `steps`: each assistant `function_call` except `Finish`, with its JSON arguments decoded and
  the following `function` message as output. The output's outer JSON layer
  (`{"error": ..., "response": ...}`) is decoded once: the output is the `response` text, and a
  non-empty `error` becomes `error: <error>\nresponse: <response>` with `is_error: true`.
  Otherwise `is_error` is left unset (upstream's empty `error` does not prove success). Upstream
  cut long observations at 1024 characters and appended `...`; those outputs keep the `...`.
- Dropped from the chain: the DFSDT feedback turns (user messages starting "This is not the
  first time you try this task", which list earlier failed branches with
  `mento-carlo-action-value` scores) and the assistant's thought text (not evidence).
- `allowed_tools`: every name in `answer_generation.function` except `Finish`.
- `final_answer`: `final_answer` from the `Finish` arguments when `return_type` is
  `give_answer`; empty when it is `give_up_and_restart` (G2 127), since no answer reached the
  user.

## What was stripped

Never read, so absent from every case: `win`, `tree` (with `Elo`, `pruned`, `is_terminal` and
the other node fields), `forward_args`, `compare_candidates`, `answer_generation.valid_data`,
`query_count`, `total_tokens`, `finish_type`, `chain`, the top-level `final_answer` copy, and the
`mento-carlo-action-value` scores inside the dropped feedback turns.

## Redactions

One set of rules (`toolbench_redact.py`) is applied twice: by the `--vendor` step to every
string in the vendored JSON (keys included, and the JSON text nested inside strings, such as
observations, along with it), and again by the converter to each case's task, system prompt,
arguments, outputs and final answer. The rules:

- every email address becomes `[email redacted]`;
- every phone number (international `+` form) becomes `[phone redacted]`;
- the name of an individual tied to contact data becomes `[name redacted]`. The names are
  listed only as sha256 digests of the lowercased word (`NAME_SHA256`), so the converter code
  doesn't republish them; any whole word with a listed digest is replaced.

The vendor step checks that every string that held JSON upstream still parses after
redaction, at every nesting level, and decodes to the redacted upstream value; outputs that
upstream cut at 1024 characters (ending `...`) were never valid JSON and stay as they were.

What it redacted in the vendored files (no other vendored file held any of these):

| File | Emails | Phone numbers | Names |
|---|---|---|---|
| G1 10 | 19 | 27 | 0 |
| G1 11 | 36 | 60 | 0 |

These are the New Caledonian customs agencies' contact details returned by the
`transitaires` tool, repeated in each observation, in the DFSDT tree and in the final answers:
three distinct email addresses (a sales address at ACT, the agency address at LTN, and one
personal work address at ATL Lines whose local part is an employee's initial and surname) and
five distinct phone numbers (the New Caledonian `+687` numbers of EKVF, ACT, AFL, LTN and ATI
Tramar). The employee's surname appears nowhere except in that address, so the email rule
removes it and the name rule finds nothing left; the rule stays as a guard, and the tests
check that no listed name is left in the vendored files or the cases.

In the cases, that touched:

| Case(s) | What was redacted |
|---|---|
| `toolbench-g1-10-faith` | Business emails and phone numbers of the agencies in both outputs and the final answer; the employee's work email in the agency list |
| `toolbench-g1-11-rec` | The same agency list (twice) and the final answer, including the same email |

No other case contained an email or phone number. Kept on purpose: agency and company names,
postal codes and the RIDET business number (public business listings, no person named; "Groupe
Léon Vincent" is a company name), the street for a Brazilian postal code (G2 52, a postal
lookup, not anyone's address), product listings and tracking/reference numbers from the queries.
No case was dropped for redaction: the claims labelled never rest on a redacted value (the
redacted email and phone claims in G1 10 are left out of its claim list). Redacting the
vendored files changed none of the 12 cases: the converter regenerates them byte for byte.
