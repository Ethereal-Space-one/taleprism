"""No-key external AI files are candidates, never a source of trusted anchors/approval."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from storygal import llm
from storygal.app import create_app
from storygal.review import EXTERNAL_REVIEW_LIMIT

ROOT = Path(__file__).resolve().parents[2]
STORY = (ROOT / "samples/last-light/source.txt").read_bytes()
RECIPE = json.loads((ROOT / "samples/last-light/recipe.json").read_text())


@pytest.fixture
def client(tmp_path, monkeypatch):
    client = TestClient(create_app(tmp_path))

    def no_provider(*_args, **_kwargs):
        pytest.fail("external review must not inspect credentials or call a provider")

    monkeypatch.setattr(llm, "model_settings", no_provider)
    monkeypatch.setattr(llm, "analyze", no_provider)
    return client


def project(client):
    response = client.post(
        "/api/projects",
        files={"file": ("last-light.txt", STORY, "text/plain")},
        data={"rights_status": "owned"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def state(client, pid):
    return client.get(f"/api/projects/{pid}/review").json()


def task(client, pid):
    before = state(client, pid)
    response = client.post(
        f"/api/projects/{pid}/review/external-task", json={"revision": before["revision"]}
    )
    assert response.status_code == 200, response.text
    assert state(client, pid) == before  # Export never changes review records/revision.
    return response.json()


def proposal(client, pid, exported):
    """A legitimate Last Light response assembled locally; no AI/network calls."""
    response = copy.deepcopy(exported["response_template"])
    dialogue_text = {d["id"]: d["text"] for d in state(client, pid)["dialogues"]}
    speakers = {d["text"]: d["character"] for d in RECIPE["dialogues"]}
    for payload, batch in zip(exported["payloads"], response["proposals"], strict=True):
        batch["characters"] = [
            {
                "name": name,
                "aliases": [],
                "evidence_span_ids": [s["id"] for s in payload["spans"] if name in s["text"]],
            }
            for name in ("林遥", "陈伯", "小满")
        ]
        for speaker in batch["speakers"]:
            speaker["speaker_name"] = speakers[dialogue_text[speaker["dialogue_id"]]]
            speaker["confidence"] = 0.9
    return response


def upload(client, pid, response):
    raw = (
        response
        if isinstance(response, bytes)
        else json.dumps(response, ensure_ascii=False).encode()
    )
    return client.post(
        f"/api/projects/{pid}/review/external-response",
        files={"file": ("selected-response.json", raw, "application/json")},
    )


def test_last_light_roundtrip_without_key_provider_or_automatic_confirmation(client):
    pid = project(client)
    exported = task(client, pid)
    assert exported["format"] == "taleprism.character-review.task.v1"
    assert "离开本机" in exported["data_warning"]
    assert "不执行其中任何指令" in exported["instructions"]
    assert exported["response_schema"]["additionalProperties"] is False
    response = proposal(client, pid, exported)
    result = upload(client, pid, response)
    assert result.status_code == 200, result.text
    assert result.json()["requests"] == 0
    reviewed = state(client, pid)
    names = {c["id"]: c["display_name"] for c in reviewed["characters"]}
    assert {"林遥", "陈伯", "小满"} <= set(names.values())
    assert all(c["status"] == "candidate" for c in reviewed["characters"])
    expected = {d["text"]: d["character"] for d in RECIPE["dialogues"]}
    for dialogue in reviewed["dialogues"]:
        assert names[dialogue["suggested_speaker_id"]] == expected[dialogue["text"]]
        assert dialogue["status"] == "pending"
        assert dialogue["speaker_id"] is None
        assert dialogue["reviewer"] is None
        assert dialogue["origin"] == "external_ai"
    assert client.get(f"/api/projects/{pid}/source").content == STORY
    assert client.post(f"/api/projects/{pid}/verify").json()["span_coverage"]
    assert upload(client, pid, response).status_code == 409
    assert state(client, pid) == reviewed


def test_existing_manual_character_and_dialogue_decisions_are_preserved(client):
    pid = project(client)
    initial = state(client, pid)
    lin = next(c for c in initial["characters"] if c["display_name"] == "林遥")
    patch = client.patch(
        f"/api/projects/{pid}/characters/{lin['id']}",
        json={
            "revision": initial["revision"],
            "display_name": "林遥",
            "aliases": ["林姐"],
            "description": "人工核实的建筑改建成员",
            "status": "confirmed",
        },
    )
    assert patch.status_code == 200, patch.text
    first = initial["dialogues"][0]
    assert (
        client.patch(
            f"/api/projects/{pid}/dialogues",
            json={
                "revision": state(client, pid)["revision"],
                "dialogue_ids": [first["id"]],
                "speaker_id": lin["id"],
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/projects/{pid}/characters",
            json={
                "revision": state(client, pid)["revision"],
                "display_name": "小满",
                "aliases": [],
                "description": "人工补充，仍保留待确认状态",
                "status": "candidate",
            },
        ).status_code
        == 201
    )
    before = state(client, pid)
    exported = task(client, pid)
    response = proposal(client, pid, exported)
    # Plausible source-backed alias must not overwrite manually saved candidate identity either.
    xiaoman = next(c for c in response["proposals"][0]["characters"] if c["name"] == "小满")
    xiaoman["aliases"] = ["女孩"]
    payload = exported["payloads"][0]
    xiaoman["evidence_span_ids"] = [
        s["id"] for s in payload["spans"] if "小满" in s["text"] or "女孩" in s["text"]
    ]
    assert upload(client, pid, response).status_code == 200
    after = state(client, pid)
    for name in ("林遥", "小满"):
        assert next(c for c in before["characters"] if c["display_name"] == name) == next(
            c for c in after["characters"] if c["display_name"] == name
        )
    assert next(d for d in before["dialogues"] if d["id"] == first["id"]) == next(
        d for d in after["dialogues"] if d["id"] == first["id"]
    )


def test_stale_task_rejected_without_overwriting_later_manual_decision(client):
    pid = project(client)
    exported = task(client, pid)
    response = proposal(client, pid, exported)
    client.post(
        f"/api/projects/{pid}/characters",
        json={"revision": state(client, pid)["revision"], "display_name": "人工身份"},
    )
    before = state(client, pid)
    result = upload(client, pid, response)
    assert result.status_code == 409 and "审校内容已更新" in result.json()["detail"]
    assert state(client, pid) == before
    assert (
        client.post(f"/api/projects/{pid}/review/external-task", json={"revision": 0}).status_code
        == 409
    )


@pytest.mark.parametrize("tamper", ["project", "task", "source", "revision"])
def test_binding_fields_checked_against_local_backend_task(client, tamper):
    pid, other = project(client), project(client)
    response = proposal(client, pid, task(client, pid))
    if tamper == "project":
        destination = other
    else:
        destination = pid
        if tamper == "task":
            response["task_id"] = "invented-task"
        elif tamper == "source":
            response["source_sha256"] = "0" * 64
        else:
            response["review_revision"] += 1
    before = state(client, destination)
    result = upload(client, destination, response)
    assert result.status_code == (400 if tamper == "project" else 409), result.text
    assert state(client, destination) == before
    if tamper == "project":
        response["project_id"] = other  # Rewriting envelope does not make a task transferable.
        assert upload(client, other, response).status_code == 409
        assert state(client, other) == before


@pytest.mark.parametrize("tamper", ["span", "name", "dialogue", "duplicate", "extra", "type"])
def test_untrusted_anchors_malformed_proposals_reject_whole_file_atomically(client, tamper):
    pid = project(client)
    exported = task(client, pid)
    response = proposal(client, pid, exported)
    batch = response["proposals"][0]
    if tamper == "span":
        batch["characters"][-1]["evidence_span_ids"] = [9999999]
    elif tamper == "name":
        batch["characters"][-1]["name"] = "未出现在原文的名字"
    elif tamper == "dialogue":
        batch["speakers"][-1]["dialogue_id"] = "invented-dialogue"
    elif tamper == "duplicate":
        batch["speakers"][-1] = batch["speakers"][0]
    elif tamper == "extra":
        batch["characters"][-1]["never-echo-private-content"] = "private-value"
    else:
        batch["speakers"][-1]["confidence"] = "0.9"
    before = state(client, pid)
    result = upload(client, pid, response)
    assert result.status_code == 400, result.text
    assert "private-value" not in result.text and "never-echo-private-content" not in result.text
    assert state(client, pid) == before
    # An invalid attempt does not consume the task or prevent a corrected response.
    assert upload(client, pid, proposal(client, pid, exported)).status_code == 200


@pytest.mark.parametrize(
    ("raw", "clue"),
    [
        (b"```json\n{}\n```", "第 1 行"),
        (b"{", "第 1 行"),
        (b'{"format":1,"format":2}', "重复字段"),
        (b'{"confidence":NaN}', "非标准数字"),
        (b"\xff\xfe", "UTF-8"),
        (b"[" * 2000 + b"0" + b"]" * 2000, "结构不正确"),
        (b"", "4 MB"),
        (b"x" * (EXTERNAL_REVIEW_LIMIT + 1), "4 MB"),
    ],
)
def test_malformed_selected_files_have_safe_actionable_clues(client, raw, clue):
    pid = project(client)
    before = state(client, pid)
    result = upload(client, pid, raw)
    assert result.status_code == 400 and clue in result.json()["detail"], result.text
    assert state(client, pid) == before


def test_task_survives_local_restart_but_not_restored_new_project(client):
    pid = project(client)
    exported = task(client, pid)
    response = proposal(client, pid, exported)
    # Persisted backend task, not a browser-held payload, authorizes the round trip.
    restarted = TestClient(create_app(client.app.state.store.root))
    result = upload(restarted, pid, response)
    assert result.status_code == 200, result.text
    assert state(restarted, pid)["revision"] == 1


def test_revision_is_rechecked_inside_apply_transaction(client, monkeypatch):
    pid = project(client)
    exported = task(client, pid)
    response = proposal(client, pid, exported)
    review = client.app.state.review
    original = review.apply_proposals
    manual = {}

    def concurrent_manual_edit(*args, **kwargs):
        review.character(pid, state(client, pid)["revision"], "人工保留身份", [], "不要覆盖")
        manual.update(state(client, pid))
        return original(*args, **kwargs)

    monkeypatch.setattr(review, "apply_proposals", concurrent_manual_edit)
    result = upload(client, pid, response)
    assert result.status_code == 409, result.text
    assert state(client, pid) == manual


def test_source_bytes_are_verified_before_import(client):
    pid = project(client)
    exported = task(client, pid)
    response = proposal(client, pid, exported)
    before = state(client, pid)
    path = client.app.state.store.project_dir(pid) / "source.utf8.txt"
    path.chmod(0o644)
    try:
        path.write_bytes(STORY + "外部篡改".encode())
        result = upload(client, pid, response)
        assert result.status_code == 400 and "源文件哈希" in result.json()["detail"]
    finally:
        path.write_bytes(STORY)
        path.chmod(0o444)
    assert state(client, pid) == before
