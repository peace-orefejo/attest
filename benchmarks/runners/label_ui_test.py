from __future__ import annotations

import http.client
import json
import re
import shutil
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import annotate
from bench_annotations import run_sha256, template
from bench_cases import Case
from bench_label_files import load_annotations
from bench_load import DATASETS_DIR, load_datasets
from label_ui_api import LabelApi, build_api
from label_ui_help import help_sections
from label_ui_page import ASSETS, page
from label_ui_server import LabelServer

TOKEN = "test-token-" + "x" * 32
SECRET = "SECRET-FROM-ANOTHER-ANNOTATOR"


class Client:
    def __init__(self, server: LabelServer) -> None:
        self.port = server.port
        self.host = f"127.0.0.1:{server.port}"

    def request(
        self,
        method: str,
        path: str,
        body: object = None,
        *,
        token: str | None = TOKEN,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any, http.client.HTTPResponse]:
        sent = {"Host": self.host, **(headers or {})}
        if token is not None:
            sent["X-Attest-Token"] = token
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            sent["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(method, path, body=data, headers=sent)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        try:
            return response.status, json.loads(raw), response
        except ValueError:
            return response.status, raw.decode(), response


@pytest.fixture
def datasets(tmp_path: Path) -> Path:
    root = tmp_path / "datasets"
    shutil.copytree(DATASETS_DIR, root)
    return root


@pytest.fixture
def labels(tmp_path: Path, datasets: Path) -> Path:
    root = tmp_path / "labels"
    argv = ["--datasets", str(datasets), "--labels", str(root), "template", "po"]
    assert annotate.main([*argv, "--check", "faithfulness", "--check", "recovery"]) == 0
    other = root / "vk"
    other.mkdir()
    blank = json.loads((root / "po" / "rec-retried.json").read_text())
    (other / "rec-retried.json").write_text(json.dumps({**blank, "rationale": SECRET}))
    (other / "vk-only.json").write_text(json.dumps({**blank, "case_id": "vk-only"}))
    return root


def _cases(datasets: Path) -> dict[str, Case]:
    loaded = load_datasets(datasets, allow_missing=True)
    return {c.id: c for by in loaded.cases.values() for cs in by.values() for c in cs}


def _api(datasets: Path, labels: Path, forbidden: Any = None) -> LabelApi:
    loaded = load_datasets(datasets, allow_missing=True)
    return build_api("po", labels / "po", loaded, forbidden=forbidden, regenerate="annotate")


@pytest.fixture
def client(datasets: Path, labels: Path) -> Iterator[Client]:
    yield from _serve(_api(datasets, labels))


def _serve(api: LabelApi) -> Iterator[Client]:
    server = LabelServer(api, token=TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Client(server)
    finally:
        server.shutdown()
        server.server_close()


def _full(case_file: dict[str, Any]) -> dict[str, Any]:
    calls = [
        {"step": call["step"], "verdict": "correct", "recovery": "none"}
        for call in case_file["labels"]["calls"]
    ]
    return {
        "labels": {"calls": calls},
        "confidence": "high",
        "ambiguous": False,
        "rationale": "both calls worked",
        "version": case_file["version"],
    }


def test_requests_need_the_token(client: Client) -> None:
    assert client.request("GET", "/api/state", token=None)[0] == 403
    assert client.request("GET", "/api/state", token="wrong")[0] == 403
    assert client.request("GET", "/", token=None)[0] == 403
    assert client.request("GET", f"/api/state?token={TOKEN}", token=None)[0] == 200
    assert client.request("GET", "/api/state")[0] == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example:80"},
        {"Host": "attacker.test"},
        {"Origin": "http://evil.example"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_wrong_host_or_origin_is_refused_even_with_the_token(
    client: Client, headers: dict[str, str]
) -> None:
    status, body, _ = client.request("GET", "/api/state", headers=headers)
    assert status == 403 and "cases" not in body


def test_own_origin_and_localhost_are_accepted(client: Client) -> None:
    origin = {"Origin": f"http://127.0.0.1:{client.port}"}
    assert client.request("GET", "/api/state", headers=origin)[0] == 200
    assert (
        client.request("GET", "/api/state", headers={"Host": f"localhost:{client.port}"})[0] == 200
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/case/vk-only",
        "/api/case/../vk/rec-retried",
        "/api/case/..%2Fvk%2Frec-retried",
        "/api/case/%2E%2E/vk/rec-retried",
        "/api/case/rec-retried.json",
        "/api/case/",
        "/../vk/rec-retried.json",
        "/vk/rec-retried.json",
        "/label_ui.js",
        "/datasets/recovery/dev.jsonl",
        "/etc/passwd",
    ],
)
def test_other_annotators_and_other_files_are_never_served(client: Client, path: str) -> None:
    status, body, _ = client.request("GET", path)
    assert status == 404
    assert SECRET not in json.dumps(body)


def test_only_own_runs_and_labels_are_sent(client: Client, datasets: Path) -> None:
    _, state, _ = client.request("GET", "/api/state")
    ids = {case["id"] for case in state["cases"]}
    assert "vk-only" not in ids and "rec-retried" in ids
    _, case, _ = client.request("GET", "/api/case/rec-retried")
    sent = json.dumps([state, case])
    original = _cases(datasets)["rec-retried"]
    assert SECRET not in sent
    for withheld in ("notes", "category", "expected", "label_status", "annotators", "origin"):
        assert f'"{withheld}"' not in sent
    assert original.notes not in sent and original.category not in sent
    assert all(call["verdict"] is None for call in case["labels"]["calls"])


def test_save_round_trip_is_accepted_by_load_annotations(
    client: Client, labels: Path, datasets: Path
) -> None:
    path = labels / "po" / "rec-retried.json"
    before = json.loads(path.read_text())
    _, case, _ = client.request("GET", "/api/case/rec-retried")
    status, result, _ = client.request("PUT", "/api/case/rec-retried", _full(case))
    assert status == 200 and result["saved"] and result["case"]["summary"]["status"] == "done"

    after = json.loads(path.read_text())
    assert list(after) == list(before)
    assert (
        after["run_sha256"] == before["run_sha256"] == run_sha256(_cases(datasets)["rec-retried"])
    )
    assert after["trajectory"] == before["trajectory"]
    assert path.read_text().endswith("\n") and after == json.loads(json.dumps(after, indent=2))
    assert [p.name for p in path.parent.iterdir() if not p.name.endswith(".json")] == []
    shutil.rmtree(labels / "vk")
    loaded = load_annotations(labels, _cases(datasets))
    annotation = loaded.annotations["po"]["rec-retried"]
    assert annotation.confidence == "high" and annotation.rationale == "both calls worked"


def test_partial_save_counts_as_unfinished(client: Client, labels: Path, datasets: Path) -> None:
    _, case, _ = client.request("GET", "/api/case/rec-retried")
    body = _full(case)
    body["labels"]["calls"][1]["recovery"] = None
    body["confidence"] = None
    status, result, _ = client.request("PUT", "/api/case/rec-retried", body)
    assert status == 200 and result["case"]["summary"]["status"] == "partial"
    shutil.rmtree(labels / "vk")
    loaded = load_annotations(labels, _cases(datasets))
    assert "rec-retried" not in loaded.annotations["po"]
    assert labels / "po" / "rec-retried.json" in loaded.unfinished


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda b: b["labels"]["calls"][0].update(verdict="fine"), "isn't a verdict"),
        (lambda b: b["labels"]["calls"].pop(), "items to label"),
        (lambda b: b["labels"]["calls"][0].update(step=99), "items to label"),
        (lambda b: b.update(confidence="very"), "confidence"),
        (lambda b: b.update(extra=1), "unknown field"),
        (lambda b: b.update(version="0" * 64), "changed on disk"),
    ],
)
def test_invalid_saves_are_refused_with_the_reason(
    client: Client, labels: Path, change: Any, message: str
) -> None:
    path = labels / "po" / "rec-retried.json"
    before = path.read_text()
    _, case, _ = client.request("GET", "/api/case/rec-retried")
    body = _full(case)
    change(body)
    status, result, _ = client.request("PUT", "/api/case/rec-retried", body)
    assert status == 422 and not result["saved"]
    assert any(message in error for error in result["errors"])
    assert path.read_text() == before


def test_faithfulness_run_label_is_refused(client: Client) -> None:
    _, state, _ = client.request("GET", "/api/state")
    case_id = next(c["id"] for c in state["cases"] if c["check"] == "faithfulness")
    _, case, _ = client.request("GET", f"/api/case/{case_id}")
    labels = {**case["labels"], "run_label": "pass"}
    body = {"labels": labels, "confidence": None, "ambiguous": False, "rationale": ""}
    status, result, _ = client.request(
        "PUT", f"/api/case/{case_id}", {**body, "version": case["version"]}
    )
    assert status == 422 and any("run_label" in error for error in result["errors"])


def test_stale_files_are_read_only(client: Client, labels: Path) -> None:
    path = labels / "po" / "rec-retried.json"
    data = json.loads(path.read_text())
    data["run_sha256"] = "0" * 64
    path.write_text(json.dumps(data, indent=2))
    _, case, _ = client.request("GET", "/api/case/rec-retried")
    assert case["summary"]["status"] == "stale"
    assert "older version" in case["summary"]["reason"]
    status, result, _ = client.request("PUT", "/api/case/rec-retried", _full(case))
    assert status == 422 and "read-only" in result["errors"][0]
    assert json.loads(path.read_text()) == data


def test_creating_label_files_reuses_the_template(tmp_path: Path, datasets: Path) -> None:
    labels = tmp_path / "fresh"
    for client in _serve(_api(datasets, labels)):
        assert client.request("GET", "/api/state")[1]["cases"] == []
        assert client.request("POST", "/api/templates", {"checks": [], "splits": ["dev"]})[0] == 400
        body = {"checks": ["recovery", "nonsense"], "splits": ["dev", "../x"]}
        status, result, _ = client.request("POST", "/api/templates", body)
        assert status == 200 and result["written"] > 0
        _, state, _ = client.request("GET", "/api/state")
        assert {c["status"] for c in state["cases"]} == {"blank"}
    cases = load_datasets(datasets).split("recovery", "dev")
    assert sorted(p.stem for p in (labels / "po").glob("*.json")) == sorted(c.id for c in cases)
    for case in cases:
        assert json.loads((labels / "po" / f"{case.id}.json").read_text()) == template(case)


def test_private_guard_blocks_writes_inside_the_repository(
    tmp_path: Path, datasets: Path, labels: Path
) -> None:
    for client in _serve(_api(datasets, labels, forbidden=lambda _: True)):
        status, result, _ = client.request(
            "POST", "/api/templates", {"checks": ["faithfulness"], "splits": ["dev"]}
        )
        assert status == 403 and "private" in result["error"]
        _, case, _ = client.request("GET", "/api/case/rec-retried")
        assert client.request("PUT", "/api/case/rec-retried", _full(case))[0] == 403


def test_serve_refuses_private_labels_inside_the_repository(
    datasets: Path, labels: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inside = annotate.REPO_DIR / "benchmarks" / "annotations" / "labels"
    with pytest.raises(SystemExit) as exit_info:
        annotate.main(["--datasets", str(datasets), "--labels", str(inside), "serve", "po"])
    assert exit_info.value.code == 2

    served: list[LabelApi] = []
    monkeypatch.setattr(annotate, "serve", lambda api, **_: served.append(api) or 0)
    argv = ["--datasets", str(datasets), "--labels", str(labels), "serve", "po", "--no-open"]
    assert annotate.main(argv) == 0
    assert served[0].store.folder == labels / "po"
    with pytest.raises(SystemExit):
        annotate.main(["--datasets", str(datasets), "--labels", str(labels), "serve", "Bad/Name"])


def test_page_loads_nothing_from_elsewhere(client: Client) -> None:
    status, body, response = client.request("GET", "/", token=None, headers={})
    assert status == 403
    status, body, response = client.request("GET", f"/?token={TOKEN}", token=None)
    assert status == 200 and "<script nonce=" in body
    assert "http://" not in body and "https://" not in body
    assert not re.search(r"(src|href)\s*=\s*[\"'](?!data:|#)", body)
    policy = response.getheader("Content-Security-Policy") or ""
    assert "default-src 'none'" in policy and "connect-src 'self'" in policy
    for asset in ("label_ui.html", "label_ui.css", "label_ui.js", "label_ui_form.js"):
        text = (ASSETS / asset).read_text()
        assert "http://" not in text and "https://" not in text
    assert page("n").count("innerHTML") == 1, "only the server-escaped guidelines use innerHTML"


def test_help_comes_from_the_guidelines() -> None:
    sections = {section.title: section for section in help_sections()}
    assert set(sections["Faithfulness"].definitions) == {"supported", "unsupported", "unverifiable"}
    assert next(iter(sections["Tool use"].definitions)) == "disallowed_tool"
    assert "Rulings log" in sections and "<table>" in sections["Rulings log"].html
    assert "<script" not in "".join(section.html for section in sections.values())
