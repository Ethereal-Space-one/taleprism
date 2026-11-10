import copy
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal import reader_export
from storygal.app import create_app
from storygal.delivery import REVIEW_CHECKS
from storygal.reader import REPO, paragraphs
from storygal.text import visible_text


@pytest.fixture
def setup(tmp_path):
    client = TestClient(create_app(tmp_path))
    raw = (REPO / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt").read_bytes()
    pid = client.post(
        "/api/projects",
        files={"file": ("reader.txt", raw)},
        data={"rights_status": "public_domain"},
    ).json()["id"]
    return client, pid, client.app.state.reader, raw


def sample_ready(setup):
    c, pid, r, raw = setup
    r.sample(pid, 0)
    for asset in r.state(pid)["assets"]:
        r.accept(pid, r.state(pid)["revision"], asset["id"], "accepted")
    return c, pid, r, raw


def export(c, pid):
    response = c.post(f"/api/projects/{pid}/reader/exports")
    assert response.status_code == 202, response.text
    return next(
        j for j in c.get(f"/api/projects/{pid}/jobs").json() if j["id"] == response.json()["job_id"]
    )


def test_original_paragraphs_bom_whitespace_and_special_text():
    raw = "\ufeff　　第一段😀 <script>原文</script>\r\n\t\n 甲曰：「保留 {变量} -next。」\t\r末段".encode()
    blocks = paragraphs(raw)
    assert "".join(b["text"] for b in blocks) == visible_text(raw.decode())
    for block in blocks:
        assert raw[block["byte_start"] : block["byte_end"]].decode() == block["text"]
    assert len(blocks) == 3


def test_candidates_preview_require_acceptance_and_repeat_reuses_files(setup):
    c, pid, r, raw = setup
    first = r.sample(pid, 0)
    ids = {a["id"] for a in first["assets"]}
    assert len(ids) == 6 and all(a["status"] == "pending" for a in first["assets"])
    content = r.content(pid)
    assert content["preview"] and len(content["config"]["scenes"]) == 10
    assert "".join(b["text"] for b in content["blocks"]) == visible_text(raw.decode())
    with pytest.raises(ValueError, match="接受"):
        r.content(pid, strict=True)
    assert {a["id"] for a in r.sample(pid, first["revision"])["assets"]} == ids
    assert c.get(f"/api/projects/{pid}/source").content == raw
    assert (
        content["map"]["phase_anchors"][0]
        < content["map"]["phase_anchors"][1]
        < content["map"]["phase_anchors"][2]
    )
    assert any(p["label"] == "乌林" for p in content["map"]["places"])


def test_scene_boundaries_cross_project_assets_and_stale_revision(setup):
    c, pid, r, _ = setup
    state = r.sample(pid, 0)
    config = copy.deepcopy(state["config"])
    config["scenes"][0]["start_byte"] += 1
    with pytest.raises(ValueError, match="首段|锚点"):
        r.save(pid, state["revision"], config)
    config = copy.deepcopy(state["config"])
    config["scenes"][0]["character_ids"] = ["unknown"]
    with pytest.raises(ValueError, match="人物不存在|角色"):
        r.save(pid, state["revision"], config)
    with pytest.raises(ValueError, match="更新"):
        r.save(pid, 0, state["config"])
    other = c.post(
        "/api/projects", files={"file": ("other.txt", b"other")}, data={"rights_status": "owned"}
    ).json()["id"]
    assert (
        c.get(f"/api/projects/{other}/reader/assets/{state['assets'][0]['id']}").status_code == 404
    )
    assert c.post(f"/api/projects/{other}/reader/sample", json={"revision": 0}).status_code == 400


def test_corrupt_image_keeps_preview_text_but_blocks_export(setup):
    c, pid, r, raw = sample_ready(setup)
    aid = r.state(pid)["config"]["scenes"][0]["asset_id"]
    path = r.path(pid, aid)
    path.chmod(0o644)
    path.write_bytes(b"broken")
    preview = r.content(pid)
    assert preview["issues"] and aid not in preview["media"]
    assert "".join(p["text"] for p in preview["blocks"]) == visible_text(raw.decode())
    assert export(c, pid)["state"] == "failed"


def test_uploaded_scene_is_pending_and_cannot_override_another_version(setup):
    c, pid, r, _ = setup
    image = Image.new("RGB", (16, 16), "navy")
    output = io.BytesIO()
    image.save(output, "PNG")
    body = {"revision": 0, "kind": "scene", "license_text": "测试图"}
    response = c.post(
        f"/api/projects/{pid}/reader/assets",
        files={"file": ("test.png", output.getvalue())},
        data=body,
    )
    assert response.status_code == 201 and response.json()["status"] == "pending"
    assert (
        c.post(
            f"/api/projects/{pid}/reader/assets",
            files={"file": ("test.png", output.getvalue())},
            data=body,
        ).status_code
        == 409
    )
    assert len(list((r.store.project_dir(pid) / "reader-assets").iterdir())) == 1


def test_standalone_reader_package_and_export_scoped_review(setup):
    c, pid, r, raw = sample_ready(setup)
    job = export(c, pid)
    assert job["state"] == "completed", job
    result = job["result"]
    assert result["format"] == "reader" and result["reader_revision"] == r.load(pid)[0]
    assert c.get(result["play_url"]).status_code == 200
    archive = r.store.project_dir(pid) / "exports" / (job["id"] + ".zip")
    with zipfile.ZipFile(archive) as z:
        data = json.loads(z.read("reader.json"))
        assert all(a["url"].startswith("./media/") for a in data["media"].values())
        assert b"storygal-reader-export" in z.read("index.html")
        assert z.read("storygal-source/original.txt") == raw
        assert "verify_package.py" in z.namelist() and "licenses/react.txt" in z.namelist()
        inventory = json.loads(z.read("storygal-delivery.json"))
        assert set(z.namelist()) == set(inventory["files"]) | {"storygal-delivery.json"}
    delivery = c.get(f"/api/projects/{pid}/delivery").json()
    assert delivery["ready"] and delivery["latest"]["kind"] == "reader_export"
    checks = {k: True for k in REVIEW_CHECKS}
    review_url = f"/api/projects/{pid}/exports/{job['id']}/review"
    assert (
        c.post(review_url, json={"checks": checks, "notes": "自动测试，非用户最终审查"}).status_code
        == 200
    )
    state = r.state(pid)
    r.save(pid, state["revision"], state["config"] | {"title": "修改后"})
    assert c.post(review_url, json={"checks": checks}).status_code == 409
    assert c.get(result["play_url"]).status_code == 200


def test_reader_change_during_packaging_never_publishes(setup, monkeypatch):
    c, pid, r, _ = sample_ready(setup)
    original = reader_export.shutil.copy2
    changed = False

    def copy_and_change(source, destination, *args, **kwargs):
        nonlocal changed
        result = original(source, destination, *args, **kwargs)
        if not changed:
            changed = True
            rev, config = r.load(pid)
            r.save(pid, rev, config | {"title": "打包中改动"})
        return result

    monkeypatch.setattr(reader_export.shutil, "copy2", copy_and_change)
    job = export(c, pid)
    assert job["state"] == "failed" and "状态" in job["error"]
    assert list((r.store.project_dir(pid) / "exports").iterdir()) == []
