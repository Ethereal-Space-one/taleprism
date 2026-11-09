import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from storygal.app import create_app

STORY = "南船距操寨止隔二里水面。黃蓋用刀一招，前船一齊發火。火趁風威，風助火勢。\n曹操與張遼引百餘騎，在火林內走。張遼指道：「只有烏林，地面空闊可走。」操逕奔烏林。\n後文另有事件。"


@pytest.fixture
def setup(tmp_path):
    client = TestClient(create_app(tmp_path))
    pid = client.post(
        "/api/projects",
        files={"file": ("visual.txt", STORY.encode())},
        data={"rights_status": "public_domain"},
    ).json()["id"]
    return client, pid, client.app.state.visual


def create_diagram(client, pid):
    rev = client.get(f"/api/projects/{pid}/visual").json()["revision"]
    r = client.post(f"/api/projects/{pid}/visual/sample-diagram", json={"revision": rev})
    assert r.status_code == 201, r.text
    return r.json()


def test_graph_requires_verbatim_evidence_and_no_spoilers(setup):
    c, pid, v = setup
    item = create_diagram(c, pid)
    bad = json.loads(json.dumps(item))
    bad["graph"]["nodes"][0]["label"] = "不存在地名"
    with pytest.raises(ValueError, match="逐字"):
        v.validate(pid, bad)
    bad = json.loads(json.dumps(item))
    bad["anchor_byte"] = c.get(f"/api/projects/{pid}/text").json()["units"][0]["byte_end"]
    with pytest.raises(ValueError, match="早于"):
        v.validate(pid, bad)
    bad = json.loads(json.dumps(item))
    bad["graph"]["edges"][0]["to_id"] = "fake"
    with pytest.raises(ValueError, match="端点"):
        v.validate(pid, bad)
    bad = json.loads(json.dumps(item))
    bad["graph"]["nodes"][0]["evidence_span_ids"] = [99999]
    with pytest.raises(ValueError):
        v.validate(pid, bad)


def test_diagram_render_confirm_stale_and_reject(setup):
    c, pid, v = setup
    item = create_diagram(c, pid)
    asset = v.asset(pid, v.state(pid)["revision"], item["id"])
    assert b"<svg" in v.path(pid, asset["id"], True).read_bytes()
    with pytest.raises(ValueError, match="逐项"):
        v.accept(pid, v.state(pid)["revision"], item["id"], "accepted", True)
    v.accept(pid, v.state(pid)["revision"], item["id"], "accepted", True, True)
    units, _ = c.app.state.review.presentation(pid)
    assert len(v.for_export(pid, units)[1]) == 1
    revision = v.state(pid)["revision"]
    reused = v.asset(pid, revision, item["id"])
    assert reused["id"] == asset["id"] and reused["reused"]
    assert v.state(pid)["revision"] == revision and v.state(pid)["items"][0]["enabled"]
    payload = {
        key: item[key] for key in ["kind", "title", "anchor_byte", "evidence_span_ids", "graph"]
    }
    payload["graph"]["edges"][0]["directed"] = True
    v.save(pid, v.state(pid)["revision"], payload, item["id"])
    current = v.state(pid)["items"][0]
    assert current["stale"] and not current["enabled"] and current["status"] == "draft"
    with pytest.raises(ValueError, match="过期"):
        v.accept(pid, v.state(pid)["revision"], item["id"], "accepted", True, True)


def test_illustration_budget_style_and_asset_integrity(setup):
    c, pid, v = setup
    v.propose(pid, 0)
    illustrations = v.state(pid)["items"]
    item = illustrations[0]
    r = c.post(
        f"/api/projects/{pid}/visual/items/{item['id']}/codex-sample",
        json={"revision": v.state(pid)["revision"]},
    )
    assert r.status_code == 201, r.text
    asset = r.json()
    v.accept(pid, v.state(pid)["revision"], item["id"], "accepted", True)
    with pytest.raises(ValueError, match="预算"):
        v.settings(pid, v.state(pid)["revision"], "ink", 0)
    v.settings(pid, v.state(pid)["revision"], "gongbi", 3)
    current = v.state(pid)["items"][0]
    assert current["stale"] and current["status"] == "draft" and not current["enabled"]
    path = v.path(pid, asset["id"])
    path.chmod(0o644)
    path.write_bytes(b"bad")
    with pytest.raises(ValueError, match="修改"):
        v.path(pid, asset["id"])


def test_export_keeps_source_and_validates_visual_program(setup):
    c, pid, v = setup
    item = create_diagram(c, pid)
    v.asset(pid, v.state(pid)["revision"], item["id"])
    v.accept(pid, v.state(pid)["revision"], item["id"], "accepted", True, True)
    c.post(f"/api/projects/{pid}/exports")
    job = c.get(f"/api/projects/{pid}/jobs").json()[0]
    assert job["state"] == "completed", job
    archive = c.app.state.store.project_dir(pid) / "exports" / (job["id"] + ".zip")
    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read("storygal-manifest.json"))
        assert manifest["checks"]["parser"]["passed"]
        assert len(manifest["visual_events"]) == 1
        assert z.read("storygal-source/original.txt") == STORY.encode()
        assert (
            len(
                [
                    f
                    for f in z.namelist()
                    if f.endswith(".svg") and f.startswith("storygal-diagrams/")
                ]
            )
            == 1
        )
        assert b"setTextbox:hide" in z.read("game/scene/start.txt")


def test_conflict_and_cross_project_asset_scope(setup):
    c, pid, v = setup
    item = create_diagram(c, pid)
    with pytest.raises(ValueError, match="更新"):
        v.settings(pid, 0, "ink", 2)
    asset = v.asset(pid, v.state(pid)["revision"], item["id"])
    other = c.post(
        "/api/projects", files={"file": ("other.txt", b"other")}, data={"rights_status": "owned"}
    ).json()["id"]
    assert c.get(f"/api/projects/{other}/visual/assets/{asset['id']}.png").status_code == 404
