from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import ClassVar

import pytest

import export_hf
from hf_build import MANIFEST, ExportError, build
from hf_card import revision_tag
from hf_manifest import Manifest
from hf_upload import MISSING_HUB, upload

REPO = "someone/attest-benchmark"
SECRET = "hf_test_token_never_printed_0123456789"


class _CommitInfo:
    oid = "abc123"


class FakeHfApi:
    calls: ClassVar[list[tuple[str, tuple[object, ...], dict[str, object]]]] = []
    fail_tag = False

    def create_repo(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("create_repo", args, kwargs))
        return f"https://huggingface.co/datasets/{args[0]}"

    def upload_folder(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("upload_folder", args, kwargs))
        return _CommitInfo()

    def create_tag(self, *args: object, **kwargs: object) -> None:
        self.calls.append(("create_tag", args, kwargs))
        if self.fail_tag:
            raise RuntimeError(f"tag exists (token {SECRET})")


@pytest.fixture
def fake_hub(monkeypatch: pytest.MonkeyPatch) -> type[FakeHfApi]:
    module = types.ModuleType("huggingface_hub")
    module.HfApi = FakeHfApi
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    monkeypatch.setenv("HF_TOKEN", SECRET)
    FakeHfApi.calls = []
    FakeHfApi.fail_tag = False
    return FakeHfApi


@pytest.fixture
def built(tmp_path: Path) -> Path:
    out = tmp_path / "export"
    build(out, repo=REPO)
    return out


def test_upload_creates_the_dataset_repo_uploads_and_tags(
    fake_hub: type[FakeHfApi], built: Path
) -> None:
    manifest = Manifest.model_validate_json((built / MANIFEST).read_text(encoding="utf-8"))
    message = upload(REPO, built, private=True)
    names = [name for name, _, _ in fake_hub.calls]
    assert names == ["create_repo", "upload_folder", "create_tag"]
    _, args, kwargs = fake_hub.calls[0]
    assert args == (REPO,)
    assert kwargs == {"repo_type": "dataset", "private": True, "exist_ok": True}
    _, _, kwargs = fake_hub.calls[1]
    assert kwargs["repo_id"] == REPO
    assert kwargs["repo_type"] == "dataset"
    assert kwargs["folder_path"] == str(built)
    assert manifest.dataset_version in str(kwargs["commit_message"])
    _, args, kwargs = fake_hub.calls[2]
    assert args == (REPO,)
    assert kwargs["tag"] == revision_tag(manifest.dataset_version)
    assert kwargs["tag"] == f"dv-{manifest.dataset_version[:12]}"
    assert kwargs["revision"] == "abc123"
    assert kwargs["repo_type"] == "dataset"
    assert "token" not in {k for _, _, call in fake_hub.calls for k in call}
    assert SECRET not in message


def test_a_failed_tag_is_reported_without_the_error_text(
    fake_hub: type[FakeHfApi], built: Path
) -> None:
    fake_hub.fail_tag = True
    message = upload(REPO, built)
    assert "tagging" in message
    assert SECRET not in message


def test_upload_refuses_a_stale_build(fake_hub: type[FakeHfApi], built: Path) -> None:
    data = built / "data" / "tool_use" / "dev.jsonl"
    data.write_text(data.read_text(encoding="utf-8")[:-1] + " \n", encoding="utf-8")
    with pytest.raises(ExportError, match=r"stale.*data/tool_use/dev\.jsonl"):
        upload(REPO, built)
    (built / "extra.txt").write_text("x")
    with pytest.raises(ExportError, match="stale"):
        upload(REPO, built)
    assert fake_hub.calls == []


def test_upload_ignores_hidden_files_a_file_manager_adds(
    fake_hub: type[FakeHfApi], built: Path
) -> None:
    (built / ".DS_Store").write_bytes(b"\0")
    upload(REPO, built)
    _, _, kwargs = fake_hub.calls[1]
    assert kwargs["ignore_patterns"] == [".*", "**/.*"]


def test_upload_refuses_a_missing_build_or_manifest(
    fake_hub: type[FakeHfApi], tmp_path: Path
) -> None:
    with pytest.raises(ExportError, match="run the build command first"):
        upload(REPO, tmp_path / "hf-build")
    assert export_hf.main(["upload", "--repo", REPO, "--dir", str(tmp_path / "hf-build")]) == 2
    (tmp_path / "empty").mkdir()
    with pytest.raises(ExportError, match="manifest"):
        upload(REPO, tmp_path / "empty")
    assert fake_hub.calls == []


def test_upload_refuses_another_repo_or_a_bad_id(fake_hub: type[FakeHfApi], built: Path) -> None:
    with pytest.raises(ExportError, match="was built for"):
        upload("other/attest-benchmark", built)
    with pytest.raises(ExportError, match="<user>/<name>"):
        upload("not-a-repo-id", built)
    assert fake_hub.calls == []


def test_upload_without_huggingface_hub_says_how_to_install(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    with pytest.raises(ExportError) as raised:
        upload(REPO, built)
    assert str(raised.value) == MISSING_HUB


def test_cli_takes_no_token_and_requires_a_repo(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        export_hf.build_parser().parse_args(["upload", "--repo", REPO, "--token", SECRET])
    with pytest.raises(SystemExit):
        export_hf.build_parser().parse_args(["upload"])
    assert SECRET not in capsys.readouterr().out


def test_cli_build_and_upload(
    fake_hub: type[FakeHfApi], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "export"
    assert export_hf.main(["build", "--out", str(out), "--repo", REPO]) == 0
    assert "dataset_version" in capsys.readouterr().out
    assert export_hf.main(["upload", "--repo", REPO, "--dir", str(out)]) == 0
    printed = capsys.readouterr()
    assert "uploaded to" in printed.out
    assert SECRET not in printed.out + printed.err
