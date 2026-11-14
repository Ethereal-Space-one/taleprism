"""Offline single-shot export and candidate loop; no model or paid service calls."""

import copy
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal.app import create_app
from storygal.text import sha256


def png(color="tan"):
    out = io.BytesIO()
    Image.new("RGB", (80, 45), color).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.setattr("storygal.app.load_env", lambda _path: None)
    monkeypatch.setattr("storygal.llm.api_key", lambda: "")
    c = TestClient(create_app(tmp_path / "work"))
    pid = c.post(
        "/api/projects",
        files={"file": ("story.txt", "第一章\n灯照着长凳。\n她摊开图纸。".encode())},
        data={"rights_status": "owned"},
    ).json()["id"]
    reader = c.app.state.reader
    image = reader.upload(pid, 0, png(), "scene", "synthetic test only")
    blocks = reader.blocks(pid)[1:]
    plan = {
        "style": "透明淡彩",
        "shots": [
            {
                "id": f"shot-{i}",
                "title": f"镜头{i}",
                "after_byte": block["byte_end"],
                "moment": block["text"],
                "evidence": block["text"],
                "framing": "平视",
                "avoid": "不提前画后续动作",
                "image_asset_id": image["id"],
                "continuity": {
                    "scene_id": "station",
                    "camera": "平视",
                    "changes": "仅人物动作改变",
                    "states": [{"object_id": "lamp", "position": "凳上方"}],
                },
            }
            for i, block in enumerate(blocks)
        ],
        "scenes": [
            {
                "id": "station",
                "title": "车站",
                "layout": "灯在凳上方",
                "reference_asset_id": image["id"],
                "objects": [{"id": "lamp", "name": "灯", "kind": "fixed", "home": "凳上方"}],
            }
        ],
    }
    return c, pid, plan, image


def state(c, pid):
    return c.get(f"/api/projects/{pid}/production").json()


def save(c, pid, plan):
    current = state(c, pid)
    r = c.put(
        f"/api/projects/{pid}/production",
        json={
            "revision": current["revision"],
            "source_sha256": current["source_sha256"],
            "plan": plan,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def tasks(c, pid):
    r = c.get(f"/api/projects/{pid}/production/tasks")
    assert r.status_code == 200, r.text
    return r.json()["tasks"]


def kit(c, pid, shot="shot-0", revision=None):
    if revision is None:
        revision = state(c, pid)["revision"]
    return c.get(f"/api/projects/{pid}/production/{shot}/kit?revision={revision}")


def action(c, pid, shot, action, **more):
    return c.post(
        f"/api/projects/{pid}/production/{shot}/{action}",
        json={"revision": state(c, pid)["revision"], **more},
    )


def test_single_shot_kit_contains_real_hash_verified_references_and_anchor(work):
    c, pid, plan, image = work
    save(c, pid, plan)
    before = state(c, pid)
    response = kit(c, pid)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        task = json.loads(archive.read("task.json"))
        assert manifest["shot_id"] == task["id"] == "shot-0"
        assert task["source_anchor"]["byte_end"] == plan["shots"][0]["after_byte"]
        assert "灯照着长凳" in task["source_anchor"]["text"]
        assert task["readiness"] == "draft" and not manifest["generation_ready"]
        assert archive.read("prompt.txt").decode() == tasks(c, pid)[0]["prompt"]
        assert manifest["assets"][0]["role"] == "environment master"
        actual = archive.read(manifest["assets"][0]["file"])
        assert actual == c.app.state.reader.path(pid, image["id"]).read_bytes()
        assert sha256(actual) == manifest["assets"][0]["sha256"]
        assert {f["path"] for f in manifest["files"]} == set(archive.namelist()) - {"manifest.json"}
        for file in manifest["files"]:
            raw = archive.read(file["path"])
            assert len(raw) == file["bytes"] and sha256(raw) == file["sha256"]
        assert task["readiness_issues"] and "草稿" in task["readiness_issues"][0]
    assert state(c, pid) == before


def test_readiness_distinguishes_complete_draft_missing_fields_and_predecessor_check(work):
    c, pid, plan, _ = work
    save(c, pid, plan)
    assert tasks(c, pid)[0]["readiness"] == "draft"
    assert tasks(c, pid)[1]["readiness"] == "blocked"
    assert "上一幅" in tasks(c, pid)[1]["blocked_reason"]
    assert action(c, pid, "shot-0", "approve").status_code == 200
    assert tasks(c, pid)[0]["generation_ready"]
    changed = state(c, pid)["plan"]
    changed["shots"][0]["evidence"] = ""
    save(c, pid, changed)
    assert tasks(c, pid)[0]["readiness"] == "blocked"
    assert not tasks(c, pid)[0]["generation_ready"]
    assert "原文依据" in tasks(c, pid)[0]["blocked_reason"]


def test_missing_corrupt_and_rejected_reference_bytes_never_enter_kit(work):
    c, pid, plan, image = work
    save(c, pid, plan)
    path = c.app.state.reader.path(pid, image["id"])
    path.chmod(0o644)
    path.write_bytes(b"changed")
    task = tasks(c, pid)[0]
    assert task["readiness"] == "blocked" and not task["reference_files"][0]["available"]
    with zipfile.ZipFile(io.BytesIO(kit(c, pid).content)) as archive:
        assert not any(name.startswith("references/") for name in archive.namelist())
        assert not json.loads(archive.read("manifest.json"))["generation_ready"]
    c.app.state.reader.accept(pid, c.app.state.reader.load(pid)[0], image["id"], "rejected")
    with zipfile.ZipFile(io.BytesIO(kit(c, pid).content)) as archive:
        assert not json.loads(archive.read("manifest.json"))["assets"]


def test_kit_rejects_stale_revision_unknown_shot_and_mid_export_change(work, monkeypatch):
    c, pid, plan, _image = work
    save(c, pid, plan)
    assert kit(c, pid, revision=0).status_code == 409
    assert kit(c, pid, shot="absent").status_code == 400
    reader = c.app.state.reader
    real = reader.path
    calls = 0

    def concurrent_path(project, aid):
        nonlocal calls
        result = real(project, aid)
        calls += 1
        # tasks first verifies both master references, then export materializes target bytes.
        if calls == 3:
            changed = copy.deepcopy(plan)
            changed["style"] = "在另一个窗口修改的画风"
            save(c, pid, changed)
        return result

    monkeypatch.setattr(reader, "path", concurrent_path)
    result = kit(c, pid)
    assert result.status_code == 409, result.text
    assert state(c, pid)["plan"]["style"] == "在另一个窗口修改的画风"


def test_character_identity_missing_is_not_ready_even_if_plan_was_approved(work):
    c, pid, plan, _ = work
    review = c.app.state.reader.review
    char = review.character(pid, review.state(pid)["revision"], "她", [], "", status="confirmed")
    plan["shots"][0]["actors"] = [
        {
            "character_id": char["id"],
            "goal": "讲解",
            "knows": "图纸内容",
            "public_face": "平静",
            "private_tension": "担忧误解",
            "visible_action": "摊开图纸",
        }
    ]
    save(c, pid, plan)
    assert action(c, pid, "shot-0", "approve").status_code == 200
    assert not tasks(c, pid)[0]["generation_ready"]
    asset = review.upload_asset(
        pid, review.state(pid)["revision"], char["id"], png("blue"), "reference", "identity test"
    )
    review.accept_asset(pid, review.state(pid)["revision"], asset["id"], "accepted", False)
    current = state(c, pid)["plan"]
    current["shots"][0]["actors"][0]["reference_asset_id"] = asset["id"]
    save(c, pid, current)
    assert action(c, pid, "shot-0", "approve").status_code == 200
    assert tasks(c, pid)[0]["generation_ready"]
    with zipfile.ZipFile(io.BytesIO(kit(c, pid).content)) as archive:
        assets = json.loads(archive.read("manifest.json"))["assets"]
        identity = next(a for a in assets if a["role"] == "character identity")
        assert archive.read(identity["file"]) == review.asset_path(pid, asset["id"]).read_bytes()


def test_candidate_upload_does_not_bind_accept_or_pass_and_save_preserves_it(work):
    c, pid, plan, _ = work
    save(c, pid, plan)
    before = state(c, pid)
    r = c.post(
        f"/api/projects/{pid}/reader/assets",
        files={"file": ("my-candidate.png", png("blue"))},
        data={
            "revision": c.app.state.reader.load(pid)[0],
            "kind": "scene",
            "license_text": "镜头「镜头0」 · my-candidate.png / synthetic test",
        },
    )
    assert r.status_code == 201, r.text
    candidate = r.json()
    assert candidate["status"] == "pending"
    assert state(c, pid) == before
    draft = copy.deepcopy(before["plan"])
    draft["shots"][0]["image_asset_id"] = candidate["id"]
    result = save(c, pid, draft)
    shot = result["plan"]["shots"][0]
    assert shot["image_asset_id"] == candidate["id"] and shot["status"] == "draft"
    assert shot["continuity_check"] is None
    assert (
        next(
            a
            for a in c.get(f"/api/projects/{pid}/reader").json()["assets"]
            if a["id"] == candidate["id"]
        )["status"]
        == "pending"
    )
