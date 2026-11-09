import copy
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal.app import create_app


@pytest.fixture
def scene(tmp_path):
    c = TestClient(create_app(tmp_path / "work"))
    raw = "第一章\n灯照着长凳。\n她摊开图纸。\n他坐下记录。".encode()
    pid = c.post(
        "/api/projects", files={"file": ("scene.txt", raw)}, data={"rights_status": "owned"}
    ).json()["id"]
    reader = c.app.state.reader
    image = io.BytesIO()
    Image.new("RGB", (80, 45), "tan").save(image, "PNG")
    asset = reader.upload(pid, 0, image.getvalue(), "scene", "test fixture")
    shots = []
    for i, block in enumerate(reader.blocks(pid)[1:]):
        shots.append(
            {
                "id": f"shot-{i}",
                "title": f"镜头{i}",
                "after_byte": block["byte_end"],
                "moment": block["text"],
                "evidence": block["text"],
                "framing": "固定机位",
                "avoid": "不提前和解",
                "image_asset_id": asset["id"],
                "continuity": {
                    "scene_id": "station",
                    "camera": "平视，不改变灯与长凳关系",
                    "changes": "只改变道具与人物动作",
                    "method": "edit",
                    "states": [
                        {"object_id": "lamp", "visibility": "visible", "position": "长凳上方"},
                        {
                            "object_id": "plan",
                            "visibility": "absent" if i == 0 else "visible",
                            "position": "尚未展开" if i == 0 else "凳面右侧",
                            "reason": "" if i == 0 else "原文写她摊开图纸",
                        },
                    ],
                },
            }
        )
    plan = {
        "scenes": [
            {
                "id": "station",
                "title": "旧站",
                "layout": "灯在凳上方",
                "reference_asset_id": asset["id"],
                "objects": [
                    {
                        "id": "lamp",
                        "name": "旧灯",
                        "kind": "fixed",
                        "home": "长凳上方",
                        "origin": "source",
                        "evidence": "灯照着长凳",
                    },
                    {"id": "plan", "name": "图纸", "kind": "movable"},
                ],
            }
        ],
        "shots": shots,
    }
    return c, pid, plan, raw


def get(c, pid):
    return c.get(f"/api/projects/{pid}/production").json()


def save(c, pid, plan):
    state = get(c, pid)
    return c.put(
        f"/api/projects/{pid}/production",
        json={"revision": state["revision"], "source_sha256": state["source_sha256"], "plan": plan},
    )


def action(c, pid, path, **extra):
    return c.post(
        f"/api/projects/{pid}/production/{path}",
        json={"revision": get(c, pid)["revision"], **extra},
    )


def reviewed(c, pid, plan):
    r = save(c, pid, plan)
    assert r.status_code == 200, r.text
    for shot in plan["shots"]:
        assert action(c, pid, shot["id"] + "/approve").status_code == 200
        r = action(
            c,
            pid,
            shot["id"] + "/continuity-check",
            notes="已核对灯、凳及道具去向，测试记录。",
            reviewer="assistant",
        )
        assert r.status_code == 200, r.text


def test_sequence_gate_tasks_upstream_invalidation_and_no_forged_checks(scene):
    c, pid, plan, raw = scene
    assert save(c, pid, plan).status_code == 200
    for s in plan["shots"]:
        assert action(c, pid, s["id"] + "/approve").status_code == 200
    assert (
        action(c, pid, "shot-1/continuity-check", notes="跳过第一幅的无效检查记录").status_code
        == 400
    )
    assert (
        action(c, pid, "apply", reader_revision=c.app.state.reader.load(pid)[0]).status_code == 400
    )
    reviewed(c, pid, plan)
    assert (
        action(c, pid, "apply", reader_revision=c.app.state.reader.load(pid)[0]).status_code == 200
    )
    tasks = c.get(f"/api/projects/{pid}/production/tasks").json()
    assert (
        tasks["tasks"][1]["continuity"]["previous_image_asset_id"]
        == plan["shots"][0]["image_asset_id"]
    )
    assert "画外不等于消失" in tasks["tasks"][1]["prompt"]
    assert (
        tasks["tasks"][1]["image_references"][0]["asset_id"] == plan["shots"][0]["image_asset_id"]
    )
    assert tasks["tasks"][1]["image_references"][1] == {
        "asset_id": plan["scenes"][0]["reference_asset_id"],
        "role": "environment master",
    }
    changed = get(c, pid)["plan"]
    changed["shots"][1]["moment"] += "注视对方"
    r = save(c, pid, changed)
    assert r.status_code == 200, r.text
    shots = r.json()["plan"]["shots"]
    assert shots[0]["continuity_check"]
    assert not shots[1]["continuity_check"] and not shots[2]["continuity_check"]
    assert shots[1]["status"] == shots[2]["status"] == "draft"
    # Scene changes invalidate every dependent shot, including review records sent by clients.
    changed = get(c, pid)["plan"]
    changed["scenes"][0]["layout"] += "；清楚标记门口"
    assert all(not s["continuity_check"] for s in save(c, pid, changed).json()["plan"]["shots"])
    assert c.get(f"/api/projects/{pid}/source").content == raw


@pytest.mark.parametrize(
    "case",
    [
        "unknown_object",
        "duplicate",
        "fixed_absent",
        "fixed_move",
        "bad_evidence",
        "foreign_reference",
    ],
)
def test_invalid_scene_declarations_rejected(scene, case):
    c, pid, plan, _ = scene
    if case == "unknown_object":
        plan["shots"][0]["continuity"]["states"][0]["object_id"] = "other"
    elif case == "duplicate":
        plan["shots"][0]["continuity"]["states"].append(
            copy.deepcopy(plan["shots"][0]["continuity"]["states"][0])
        )
    elif case == "fixed_absent":
        plan["shots"][0]["continuity"]["states"][0]["visibility"] = "absent"
    elif case == "fixed_move":
        plan["shots"][0]["continuity"]["states"][0]["position"] = "忽然在门外"
    elif case == "bad_evidence":
        plan["scenes"][0]["objects"][0]["evidence"] = "不存在的原文"
    else:
        plan["scenes"][0]["reference_asset_id"] = "foreign"
    assert save(c, pid, plan).status_code == 400


def test_offscreen_is_not_absent_and_changes_require_reason(scene):
    c, pid, plan, _ = scene
    plan["shots"][1]["continuity"]["states"][0].update(
        visibility="offscreen", reason="机位取景裁掉上方，灯仍在原处"
    )
    plan["shots"][2]["continuity"]["states"][0]["reason"] = "镜头拉远，灯重新入画"
    reviewed(c, pid, plan)
    changed = get(c, pid)["plan"]
    changed["shots"][1]["continuity"]["states"][0]["reason"] = ""
    assert save(c, pid, changed).status_code == 200
    assert action(c, pid, "shot-1/approve").status_code == 400


def test_continuity_bundle_roundtrip_and_external_plan_cannot_import_check(scene, tmp_path):
    c, pid, plan, _ = scene
    reviewed(c, pid, plan)
    state = get(c, pid)
    external = c.post(
        f"/api/projects/{pid}/production/validate",
        json={k: state[k] for k in ["revision", "source_sha256", "plan"]},
    )
    assert external.status_code == 200
    assert all(
        s["continuity_check"] is None and s["status"] == "draft" for s in external.json()["shots"]
    )
    raw = c.get(f"/api/projects/{pid}/bundle").content
    other = TestClient(create_app(tmp_path / "other"))
    r = other.post("/api/project-bundles", files={"file": ("project.zip", raw)})
    assert r.status_code == 201, r.text
    restored = get(other, r.json()["id"])["plan"]
    assert restored == state["plan"]
    assert restored["shots"][0]["continuity_check"]["reviewer"] == "assistant"
    assert other.get(f"/api/projects/{r.json()['id']}/delivery").json()["records"] == []


@pytest.mark.parametrize("changed", ["recipe", "image"])
def test_rebuild_rejects_changed_prechecked_recipe_before_http(tmp_path, monkeypatch, changed):
    import hashlib
    import importlib.util
    import json

    from storygal.reader import REPO

    spec = importlib.util.spec_from_file_location(
        "content_builder", REPO / "tools/build_content_pack.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "image.png").write_bytes(b"original image")
    recipe = {
        "scenes": [{"id": "station"}],
        "continuity_review": "review.json",
        "shots": [{"id": "one", "continuity": {"scene_id": "station"}}],
        "images": [{"file": "image.png"}],
    }
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(recipe))
    (tmp_path / "review.json").write_text(
        json.dumps(
            {
                "recipe_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "reviewer": "assistant",
                "notes": {"one": "这是已看过原图片的制作检查记录"},
                "images": {"image.png": hashlib.sha256(b"original image").hexdigest()},
            }
        )
    )
    if changed == "recipe":
        recipe["style"] = "changed"
        path.write_text(json.dumps(recipe))
    else:
        (tmp_path / "image.png").write_bytes(b"different image")

    def no_http(*args, **kwargs):
        pytest.fail("changed source must not create a project")

    monkeypatch.setattr(module.httpx, "Client", no_http)
    with pytest.raises(ValueError, match="检查失效"):
        module.build(path, "http://localhost", tmp_path / "out.zip")
