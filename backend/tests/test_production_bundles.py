import copy
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal.app import create_app
from storygal.reader import REPO
from storygal.text import sha256


@pytest.fixture
def setup(tmp_path):
    c = TestClient(create_app(tmp_path / "first"))
    raw = "第一章　回家\n林遥说：「先听听您的想法。」陈伯握着雨伞。\n雨慢慢停了。".encode()
    p = c.post(
        "/api/projects", files={"file": ("new.txt", raw)}, data={"rights_status": "owned"}
    ).json()
    pid = p["id"]
    r = c.app.state.reader
    b = r.blocks(pid)[1]
    shot = {
        "id": "conversation",
        "title": "听见",
        "after_byte": b["byte_end"],
        "moment": "提问后等待回应",
        "evidence": "陈伯握着雨伞",
        "framing": "两张脸可读的斜侧双人近景",
        "avoid": "不能提前画出雨停与和解",
    }
    return c, pid, raw, {"style": "现代淡彩", "budget": 2, "shots": [shot]}


def save(c, pid, plan, revision=0):
    state = c.get(f"/api/projects/{pid}/production").json()
    return c.put(
        f"/api/projects/{pid}/production",
        json={"revision": revision, "source_sha256": state["source_sha256"], "plan": plan},
    )


def test_plan_anchor_evidence_approval_and_edit_invalidation(setup):
    c, pid, raw, plan = setup
    prefix = f"/api/projects/{pid}/production"
    assert save(c, pid, plan).status_code == 200
    response = c.post(prefix + "/conversation/approve", json={"revision": 1})
    assert response.status_code == 200, response.text
    assert response.json()["plan"]["shots"][0]["status"] == "approved"
    changed = response.json()["plan"]
    changed["shots"][0]["moment"] = "注视对方"
    assert save(c, pid, changed, 2).json()["plan"]["shots"][0]["status"] == "draft"
    assert save(c, pid, plan, 0).status_code == 409
    changed["shots"][0]["evidence"] = "下一章才发生的事"
    assert save(c, pid, changed, 3).status_code == 400
    assert c.get(f"/api/projects/{pid}/source").content == raw


def test_plan_foreign_source_actor_and_budget_rejected(setup):
    c, pid, _, plan = setup
    bad = copy.deepcopy(plan)
    bad["budget"] = 0
    assert save(c, pid, bad).status_code == 400
    bad = copy.deepcopy(plan)
    bad["shots"][0]["actors"] = [{"character_id": "foreign"}]
    assert save(c, pid, bad).status_code == 400
    assert (
        c.put(
            f"/api/projects/{pid}/production",
            json={"revision": 0, "source_sha256": "wrong", "plan": plan},
        ).status_code
        == 400
    )
    bad = copy.deepcopy(plan)
    bad["shots"][0]["after_byte"] -= 1
    assert save(c, pid, bad).status_code == 400


def test_plan_apply_and_task_export(setup):
    c, pid, raw, plan = setup
    r = c.app.state.reader
    out = io.BytesIO()
    Image.new("RGB", (80, 45), "teal").save(out, "PNG")
    asset = r.upload(pid, 0, out.getvalue(), "scene", "test fixture")
    plan["shots"][0]["image_asset_id"] = asset["id"]
    assert save(c, pid, plan).status_code == 200
    prefix = f"/api/projects/{pid}/production"
    assert c.post(prefix + "/conversation/approve", json={"revision": 1}).status_code == 200
    response = c.post(prefix + "/apply", json={"revision": 2, "reader_revision": r.load(pid)[0]})
    assert response.status_code == 200, response.text
    assert r.load(pid)[1]["illustrations"][0]["image_asset_id"] == asset["id"]
    assert r.content(pid)["preview"]
    assert "不能提前" in c.get(prefix + "/tasks").json()["tasks"][0]["prompt"]
    assert c.get(prefix + "/tasks?kind=plan").json()["source_sha256"] == sha256(raw)


def test_editable_bundle_roundtrip_in_clean_store(setup, tmp_path):
    c, pid, raw, plan = setup
    assert save(c, pid, plan).status_code == 200
    archive = c.get(f"/api/projects/{pid}/bundle")
    assert archive.status_code == 200, archive.text[:100] if archive.status_code != 200 else ""
    other = TestClient(create_app(tmp_path / "other"))
    response = other.post("/api/project-bundles", files={"file": ("project.zip", archive.content)})
    assert response.status_code == 201, response.text
    new = response.json()["id"]
    assert new != pid
    assert other.get(f"/api/projects/{new}/source").content == raw
    assert (
        other.get(f"/api/projects/{new}/production").json()["plan"]
        == c.get(f"/api/projects/{pid}/production").json()["plan"]
    )
    assert other.get(f"/api/projects/{new}/jobs").json() == []
    assert other.get(f"/api/projects/{new}/reader/content").status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert not any("sqlite" in n or "cache" in n or "audit" in n for n in z.namelist())


def repack(raw, mutate):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files = {n: z.read(n) for n in z.namelist() if n != "manifest.json"}
    mutate(files)
    files["manifest.json"] = json.dumps(
        {
            "format": "storygal-project-inventory",
            "version": 1,
            "files": {n: sha256(v) for n, v in files.items()},
        }
    ).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for n, data in files.items():
            z.writestr(n, data)
    return out.getvalue()


@pytest.mark.content_pack
@pytest.mark.skipif(
    not (REPO / "samples/content-packs/last-light.storygal.zip").exists(),
    reason="optional local historical sample pack",
)
def test_real_modern_pack_migrates_audio_and_exports_without_sample_keys(tmp_path, monkeypatch):
    from storygal import speech

    c = TestClient(create_app(tmp_path / "clean"))
    raw = (REPO / "samples/content-packs/last-light.storygal.zip").read_bytes()
    r = c.post("/api/project-bundles", files={"file": ("pack.zip", raw)})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    original_caps = speech.capabilities()
    monkeypatch.setattr(
        speech,
        "capabilities",
        lambda: original_caps | {"model": "different-os", "available": False, "voices": []},
    )
    content = c.get(f"/api/projects/{pid}/reader/content").json()
    assert len(content["config"]["illustrations"]) == 3
    assert len([a for a in content["media"].values() if a["type"] == "audio"]) == 2
    for a in content["media"].values():
        response = c.get(a["url"])
        assert response.status_code == 200 and sha256(response.content) == a["sha256"]
    c.post(f"/api/projects/{pid}/reader/exports")
    job = c.get(f"/api/projects/{pid}/jobs").json()[0]
    assert job["state"] == "failed", job
    prefix = f"/api/projects/{pid}/production"
    state = c.get(prefix).json()
    assert all(s["continuity_check"]["status"] == "stale" for s in state["plan"]["shots"])
    # Legacy audio remains portable, but missing visual evidence must be renewed.
    # These are synthetic workflow confirmations in a temporary regression project.
    for shot in state["plan"]["shots"]:
        response = c.post(
            prefix + "/" + shot["id"] + "/continuity-check",
            json={
                "revision": c.get(prefix).json()["revision"],
                "decision": "passed",
                "reviewer": "assistant",
                "notes": "临时回归测试：验证旧工程复核操作，不构成作品艺术验收。",
            },
        )
        assert response.status_code == 200, response.text
    c.post(f"/api/projects/{pid}/reader/exports")
    job = c.get(f"/api/projects/{pid}/jobs").json()[0]
    assert job["state"] == "completed", job
    # Editing the pronunciation must invalidate the imported acceptance too.
    _rev, config = c.app.state.speech.load(pid)
    did = next(iter(config["lines"]))
    key = next(iter(config["lines"][did]["accepted"]))
    config["lines"][did]["overrides"][key] = "这句已经改变。"
    with c.app.state.store.db() as db:
        db.execute("UPDATE speech_states SET data=? WHERE project_id=?", (json.dumps(config), pid))
    line = next(l for l in c.app.state.speech.state(pid)["lines"] if l["id"] == did)
    assert not line["segments"][0]["accepted"]


def test_ai_plan_stale_response_and_invalid_response_preserve_manual_work(setup, monkeypatch):
    from storygal import production

    c, pid, _, plan = setup
    assert save(c, pid, plan).status_code == 200
    instance = c.app.state.production
    monkeypatch.setattr(production.llm, "api_key", lambda: "fake-test-only")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(production.httpx, "Client", Client)
    before = instance.load(pid)
    with pytest.raises(ValueError):
        instance.generate(pid, 1)
    assert instance.load(pid) == before
    with pytest.raises(ValueError, match="已更新"):
        instance.generate(pid, 0)


@pytest.mark.content_pack
@pytest.mark.skipif(
    not (REPO / "samples/content-packs/chibi.storygal.zip").exists(),
    reason="optional local historical sample pack",
)
def test_legacy_chibi_pack_keeps_source_and_pending_art(tmp_path):
    c = TestClient(create_app(tmp_path / "chibi"))
    raw = (REPO / "samples/content-packs/chibi.storygal.zip").read_bytes()
    r = c.post("/api/project-bundles", files={"file": ("chibi.zip", raw)})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert (
        c.get(f"/api/projects/{pid}/source").content
        == (REPO / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt").read_bytes()
    )
    content = c.get(f"/api/projects/{pid}/reader/content").json()
    assert len(content["config"]["illustrations"]) == 12
    assert content["preview"]
    assert len(c.app.state.reader.load(pid)[1]["presentations"]) == 55
    assert c.get(f"/api/projects/{pid}/delivery").json()["records"] == []


def test_ai_task_schema_refs_resolve_and_late_model_result_cannot_overwrite(setup, monkeypatch):
    from storygal import production

    c, pid, _, plan = setup
    instance = c.app.state.production
    schema = instance.ai_task(pid)["schema"]

    def check_refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = schema
                for key in node["$ref"].removeprefix("#/").split("/"):
                    target = target[key]
            for value in node.values():
                check_refs(value)
        elif isinstance(node, list):
            for value in node:
                check_refs(value)

    check_refs(schema)
    source_hash = instance.state(pid)["source_sha256"]
    monkeypatch.setattr(production.llm, "api_key", lambda: "fake-test-only")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps({"source_sha256": source_hash, "plan": plan})
                        },
                    }
                ]
            }

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            manual = copy.deepcopy(plan)
            manual["style"] = "人工刚刚修改的新画风"
            instance.save(pid, 0, source_hash, manual)
            return Response()

    monkeypatch.setattr(production.httpx, "Client", Client)
    with pytest.raises(production.ConflictError):
        instance.generate(pid, 0)
    assert instance.load(pid)[1]["style"] == "人工刚刚修改的新画风"


@pytest.mark.parametrize("failure", ["traversal", "source", "dialogue", "version", "json_root"])
def test_bundle_rejects_bad_paths_source_records_and_versions_without_project(setup, failure):
    c, pid, _, _ = setup
    raw = c.get(f"/api/projects/{pid}/bundle").content

    def corrupt(files):
        if failure == "traversal":
            files["../escape"] = b"bad"
        elif failure == "json_root":
            files["project.json"] = b"[]"
        elif failure == "source":
            files["source.utf8.txt"] = b"not the original"
        else:
            data = json.loads(files["project.json"])
            if failure == "version":
                data["version"] = 999
            else:
                data["records"]["dialogues"][0]["text"] = "modified novel"
            files["project.json"] = json.dumps(data).encode()

    before = c.get("/api/projects").json()
    r = c.post("/api/project-bundles", files={"file": ("bad.zip", repack(raw, corrupt))})
    assert r.status_code == 400, r.text
    assert c.get("/api/projects").json() == before
    assert (
        not list((c.app.state.store.root / ".imports").glob("tmp*"))
        if (c.app.state.store.root / ".imports").exists()
        else True
    )
