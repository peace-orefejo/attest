"""Upload a built export folder to the Hugging Face Hub as a dataset repository.

`huggingface_hub` is optional (`uv sync --group hf`) and imported only here, when uploading.
The token comes from `hf auth login` or `HF_TOKEN`, read by `huggingface_hub` itself: it is
never taken as an argument and never printed.
"""

from __future__ import annotations

import importlib
import json
import re
import tempfile
from pathlib import Path
from typing import Protocol, cast

from pydantic import ValidationError

from hf_build import DEFAULT_OUT, MANIFEST, ExportError, build
from hf_card import revision_tag
from hf_manifest import Manifest

REPO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
HIDDEN = [".*", "**/.*"]
"""Files such as `.DS_Store` that a file manager may add; never compared or uploaded."""
MISSING_HUB = (
    "huggingface_hub is not installed. Install it with `uv sync --group hf`, log in with "
    "`uv run --group hf hf auth login`, then run the upload with `uv run --group hf ...`."
)


class HubApi(Protocol):
    """The part of `huggingface_hub.HfApi` the upload uses."""

    def create_repo(
        self, repo_id: str, *, repo_type: str, private: bool, exist_ok: bool
    ) -> object: ...

    def upload_folder(
        self,
        *,
        repo_id: str,
        folder_path: str,
        repo_type: str,
        commit_message: str,
        delete_patterns: list[str],
        ignore_patterns: list[str],
    ) -> object: ...

    def create_tag(
        self,
        repo_id: str,
        *,
        tag: str,
        tag_message: str,
        revision: str | None,
        repo_type: str,
        exist_ok: bool,
    ) -> None: ...


def upload(repo: str, folder: Path = DEFAULT_OUT, *, private: bool = False) -> str:
    """Upload `folder` to the dataset repo `repo` and tag the revision; return a summary.

    Refuses a missing folder, a folder built for another repo, and a stale build (one that
    differs from a fresh build of the current checkout)."""
    if REPO_ID.fullmatch(repo) is None:
        raise ExportError(f"{repo!r}: give the repository as <user>/<name>")
    manifest = verified_manifest(folder, repo)
    api = hub_api()
    api.create_repo(repo, repo_type="dataset", private=private, exist_ok=True)
    info = api.upload_folder(
        repo_id=repo,
        folder_path=str(folder),
        repo_type="dataset",
        commit_message=f"Export attest benchmark, dataset_version {manifest.dataset_version}",
        delete_patterns=["data/**", "LICENSES/**"],
        ignore_patterns=HIDDEN,
    )
    commit = getattr(info, "oid", None)
    tag = revision_tag(manifest.dataset_version)
    try:
        api.create_tag(
            repo,
            tag=tag,
            tag_message=f"dataset_version {manifest.dataset_version}",
            revision=commit if isinstance(commit, str) else None,
            repo_type="dataset",
            exist_ok=True,
        )
    except Exception as exc:  # the upload itself succeeded; a tag is only a convenience
        return f"uploaded to {repo}, but tagging {tag} failed: {type(exc).__name__}"
    return f"uploaded to {repo} and tagged {tag} (dataset_version {manifest.dataset_version})"


def verified_manifest(folder: Path, repo: str) -> Manifest:
    """The folder's manifest, after checking it is a current build made for `repo`."""
    if not folder.is_dir():
        raise ExportError(f"{folder}: no export folder; run the build command first")
    manifest = read_manifest(folder)
    if manifest.hf_repo != repo:
        raise ExportError(
            f"{folder} was built for {manifest.hf_repo}, not {repo}; build again with "
            f"--repo {repo} so the dataset card's examples name the right repository"
        )
    with tempfile.TemporaryDirectory() as fresh:
        build(Path(fresh) / "export", repo=repo)
        differences = folder_differences(folder, Path(fresh) / "export")
    if differences:
        raise ExportError(
            f"{folder} is stale: it differs from a fresh build of this checkout in "
            f"{', '.join(differences)}; run the build command again"
        )
    return manifest


def read_manifest(folder: Path) -> Manifest:
    path = folder / MANIFEST
    try:
        return Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        raise ExportError(f"{path}: missing or unreadable manifest; build again") from exc


def folder_differences(built: Path, fresh: Path) -> list[str]:
    """Every file path that is missing from one folder or whose bytes differ."""
    ours, theirs = _files(built), _files(fresh)
    return sorted(
        name
        for name in ours.keys() | theirs.keys()
        if name not in ours or name not in theirs or ours[name] != theirs[name]
    )


def hub_api() -> HubApi:
    try:
        hub = importlib.import_module("huggingface_hub")
    except ImportError as exc:
        raise ExportError(MISSING_HUB) from exc
    return cast(HubApi, hub.HfApi())


def _files(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(folder).parts)
    }
