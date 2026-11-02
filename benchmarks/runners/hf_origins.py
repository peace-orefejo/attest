"""Provenance, licence and citation for each origin the Hugging Face export may contain.

An origin missing here can't be exported: the build refuses rather than publish cases whose
licence nobody wrote down. The upstream commits must match `sources/<origin>/SOURCE.md`, and the
BibTeX entries are copied from each upstream README at that commit.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from bench_cases import SEED_ORIGIN

REPO_URL = "https://github.com/peace-orefejo/attest"
BLOB_URL = f"{REPO_URL}/blob/main"
BENCHMARKS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BENCHMARKS_DIR.parent
SOURCES_DIR = BENCHMARKS_DIR / "sources"
DATA_LICENCE = "CC-BY-4.0"
"""The licence of the benchmark's own data: the seed cases and every case's labels, notes and
conversion. The code is AGPL-3.0; upstream run content keeps its upstream licence."""
DATA_HUB_LICENCE = "cc-by-4.0"


class OriginInfo(BaseModel):
    """What the dataset card and the LICENSES folder say about one origin."""

    model_config = ConfigDict(frozen=True)

    name: str
    title: str
    licence: str
    hub_licence: str
    """The licence's identifier in Hugging Face card metadata."""
    upstream_url: str | None = None
    upstream_commit: str | None = None
    licence_file: Path
    notice_file: Path | None = None
    description: str
    bibtex: str | None = None

    @property
    def source_link(self) -> str | None:
        if self.upstream_url is None:
            return None
        return f"{BLOB_URL}/benchmarks/sources/{self.name}/SOURCE.md"


ORIGINS: dict[str, OriginInfo] = {
    SEED_ORIGIN: OriginInfo(
        name=SEED_ORIGIN,
        title="attest seed cases",
        licence=DATA_LICENCE,
        hub_licence=DATA_HUB_LICENCE,
        licence_file=BENCHMARKS_DIR / "datasets" / "LICENSE",
        description=(
            "Short synthetic runs written for attest by the benchmark author, licensed under "
            "CC BY 4.0 like the rest of the benchmark's own data."
        ),
    ),
    "tau-bench": OriginInfo(
        name="tau-bench",
        title="τ-bench",
        licence="MIT",
        hub_licence="mit",
        upstream_url="https://github.com/sierra-research/tau-bench",
        upstream_commit="59a200c6d575d595120f1cb70fea53cef0632f6b",
        licence_file=SOURCES_DIR / "tau-bench" / "LICENSE",
        notice_file=SOURCES_DIR / "tau-bench" / "NOTICE",
        description=(
            "Runs converted from τ-bench's public gpt-4o historical trajectories (retail and "
            "airline). τ-bench's rewards and task info were removed. The data is synthetic "
            "(generated users and bookings)."
        ),
        bibtex="""@misc{yao2024tau,
      title={$\\tau$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains},
      author={Shunyu Yao and Noah Shinn and Pedram Razavi and Karthik Narasimhan},
      year={2024},
      eprint={2406.12045},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2406.12045},
}""",
    ),
    "agentdojo": OriginInfo(
        name="agentdojo",
        title="AgentDojo",
        licence="MIT",
        hub_licence="mit",
        upstream_url="https://github.com/ethz-spylab/agentdojo",
        upstream_commit="089ed468cf3ed0322acc66b0211f26d9d90dbf60",
        licence_file=SOURCES_DIR / "agentdojo" / "LICENSE",
        notice_file=SOURCES_DIR / "agentdojo" / "NOTICE",
        description=(
            "Runs converted from AgentDojo's public gpt-4o-2024-05-13 runs, with and without "
            "prompt-injection attacks. AgentDojo's utility and security grades were removed. "
            "The data is synthetic (fictional users, IBANs and email addresses)."
        ),
        bibtex="""@inproceedings{
 debenedetti2024agentdojo,
 title={AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for {LLM} Agents},
 author={Edoardo Debenedetti and Jie Zhang and Mislav Balunovic and Luca Beurer-Kellner and Marc Fischer and Florian Tram{\\`e}r},
 booktitle={The Thirty-eight Conference on Neural Information Processing Systems Datasets and Benchmarks Track},
 year={2024},
 url={https://openreview.net/forum?id=m1YYAQjO3w}
}""",  # noqa: E501
    ),
    "toolbench": OriginInfo(
        name="toolbench",
        title="ToolBench",
        licence="Apache-2.0",
        hub_licence="apache-2.0",
        upstream_url="https://github.com/OpenBMB/ToolBench",
        upstream_commit="d56fdd89faf8c91fa135090b212bb9057ee5cfc2",
        licence_file=SOURCES_DIR / "toolbench" / "LICENSE",
        notice_file=SOURCES_DIR / "toolbench" / "NOTICE",
        description=(
            "Runs converted from the answer samples in ToolBench's repository (ChatGPT DFSDT "
            "searches over RapidAPI tools). Contact details (email addresses and phone numbers, "
            "one email naming an individual) were redacted, and search-tree and reward fields "
            "dropped."
        ),
        bibtex="""@misc{qin2023toolllm,
      title={ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs},
      author={Yujia Qin and Shihao Liang and Yining Ye and Kunlun Zhu and Lan Yan and Yaxi Lu and Yankai Lin and Xin Cong and Xiangru Tang and Bill Qian and Sihan Zhao and Runchu Tian and Ruobing Xie and Jie Zhou and Mark Gerstein and Dahai Li and Zhiyuan Liu and Maosong Sun},
      year={2023},
      eprint={2307.16789},
      archivePrefix={arXiv},
      primaryClass={cs.AI}
}""",  # noqa: E501
    ),
}

ATTEST_BIBTEX = f"""@software{{orefejo_attest,
  author = {{Orefejo, Adepeju}},
  title = {{attest: evidence-grounded evaluation for AI agents}},
  url = {{{REPO_URL}}},
  license = {{AGPL-3.0-only}}
}}"""


def licence_name(origin: str) -> str:
    """The file name an origin's licence gets in the export's LICENSES folder."""
    return f"{origin}.txt"


def notice_name(origin: str) -> str:
    return f"{origin}-NOTICE.txt"
