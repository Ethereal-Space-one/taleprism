import copy
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal.app import create_app


@pytest.fixture(autouse=True)
def no_model_or_local_secrets(monkeypatch):
    monkeypatch.setattr("storygal.app.load_env", lambda _path: None)
    monkeypatch.setattr("storygal.llm.api_key", lambda: "")


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
    if path.endswith("/continuity-check"):
        extra.setdefault("decision", "passed")
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


def add_character_reference(c, pid, name="她", color="blue"):
    review = c.app.state.reader.review
    char = review.character(pid, review.state(pid)["revision"], name, [], "合成人物")
    return char["id"], add_reference(c, pid, char["id"], color)


def add_reference(c, pid, cid, color):
    review = c.app.state.reader.review
    image = io.BytesIO()
    Image.new("RGB", (20, 30), color).save(image, "PNG")
    asset = review.upload_asset(
        pid,
        review.state(pid)["revision"],
        cid,
        image.getvalue(),
        "reference_and_figure",
        "synthetic",
    )
    review.accept_asset(pid, review.state(pid)["revision"], asset["id"], "accepted", True)
    return asset


def test_explicit_rejection_revokes_dependents_and_blocks_apply(scene):
    c, pid, plan, _ = scene
    reviewed(c, pid, plan)
    # Notes alone (positive or negative) never create a passing decision.
    before = get(c, pid)
    for notes in ["人物位置不对，本次检查不通过。", "已看过全部画面，连续性核对完成。"]:
        omitted = c.post(
            f"/api/projects/{pid}/production/shot-0/continuity-check",
            json={"revision": before["revision"], "notes": notes},
        )
        assert omitted.status_code == 422
        assert get(c, pid) == before
    response = action(
        c,
        pid,
        "shot-0/continuity-check",
        decision="rejected",
        notes="人物位置不对，本次检查不通过。",
    )
    assert response.status_code == 200, response.text
    shots = response.json()["plan"]["shots"]
    assert shots[0]["continuity_check"]["status"] == "rejected"
    assert all(s["continuity_check"]["status"] == "revoked" for s in shots[1:])
    assert c.get(f"/api/projects/{pid}/production/tasks").json()["tasks"][1]["blocked"]
    assert (
        action(c, pid, "apply", reader_revision=c.app.state.reader.load(pid)[0]).status_code == 400
    )


def test_reference_switch_requires_recheck_even_after_switching_back(scene):
    c, pid, plan, _ = scene
    cid, original = add_character_reference(c, pid)
    plan["shots"][0]["actors"] = [{"character_id": cid}]
    reviewed(c, pid, plan)
    add_reference(c, pid, cid, "red")
    review = c.app.state.reader.review
    review.accept_asset(pid, review.state(pid)["revision"], original["id"], "accepted", True)
    assert (
        action(c, pid, "apply", reader_revision=c.app.state.reader.load(pid)[0]).status_code == 400
    )
    assert get(c, pid)["plan"]["shots"][0]["continuity_check"]["status"] == "stale"


def test_reference_basis_matches_task_and_invalidation_is_dependency_scoped(scene):
    c, pid, plan, _ = scene
    cid, portrait = add_character_reference(c, pid)
    plan["shots"][1]["actors"] = [{"character_id": cid}]
    reviewed(c, pid, plan)
    before = get(c, pid)
    tasks = c.get(f"/api/projects/{pid}/production/tasks").json()["tasks"]
    basis = before["plan"]["shots"][1]["continuity_check"]["basis"]
    assert basis["version"] == 1
    assert basis["source_sha256"] == before["source_sha256"]
    assert (
        basis["character_references"]
        == tasks[1]["references"]
        == [{"character_id": cid, "figure_asset_id": portrait["id"], "sha256": portrait["sha256"]}]
    )
    assert tasks[1]["image_references"][-1]["sha256"] == portrait["sha256"]
    # A different person's enabled picture never participated in these checks.
    outsider, _ = add_character_reference(c, pid, "旁人", "green")
    add_reference(c, pid, outsider, "yellow")
    assert get(c, pid) == before
    add_reference(c, pid, cid, "red")
    changed = get(c, pid)
    assert changed["revision"] == before["revision"] + 1
    checks = [s["continuity_check"] for s in changed["plan"]["shots"]]
    assert [check["status"] for check in checks] == ["passed", "stale", "stale"]
    assert checks[1]["basis"] == basis  # Never backfill the new reference as checked.


def test_revoke_conflicts_reason_and_client_forgery_cannot_restore_checks(scene):
    c, pid, plan, _ = scene
    # A separate scene must retain its independent check.
    plan["scenes"].append({**copy.deepcopy(plan["scenes"][0]), "id": "other"})
    plan["shots"][2]["continuity"]["scene_id"] = "other"
    reviewed(c, pid, plan)
    old = get(c, pid)
    notes = "撤销先前结论，灯的位置需要修正。"
    response = action(c, pid, "shot-0/continuity-check", decision="revoked", notes=notes)
    assert response.status_code == 200, response.text
    shots = response.json()["plan"]["shots"]
    assert [s["continuity_check"]["status"] for s in shots] == ["revoked", "revoked", "passed"]
    assert shots[0]["continuity_check"]["notes"] == notes
    assert notes in shots[1]["continuity_check"]["invalidated_reason"]
    # A stale tab cannot overwrite a rejection, and even a fresh PUT cannot forge checks.
    assert (
        c.post(
            f"/api/projects/{pid}/production/shot-0/continuity-check",
            json={
                "revision": old["revision"],
                "decision": "passed",
                "notes": "不能从旧标签页覆盖撤销的检查记录",
            },
        ).status_code
        == 409
    )
    forged = save(c, pid, old["plan"])
    assert forged.status_code == 200
    assert forged.json()["plan"]["shots"][0]["continuity_check"]["status"] == "revoked"
    assert (
        action(c, pid, "shot-0/continuity-check", decision="rejected", notes=" " * 8).status_code
        == 422
    )
    assert (
        action(
            c,
            pid,
            "shot-0/continuity-check",
            decision="passed",
            notes="已逐项看过画面，现在可以通过复核。",
        ).status_code
        == 200
    )
    assert get(c, pid)["plan"]["shots"][1]["continuity_check"]["status"] == "revoked"


def store_plan(c, pid, plan):
    with c.app.state.store.db() as db:
        db.execute(
            "UPDATE production_states SET data=? WHERE project_id=?", (json.dumps(plan), pid)
        )


def test_legacy_check_is_readable_but_never_backfilled_or_reused(scene):
    c, pid, plan, _ = scene
    reviewed(c, pid, plan)
    old = get(c, pid)["plan"]
    for shot in old["shots"]:
        shot["continuity_check"] = {
            k: shot["continuity_check"][k]
            for k in ["fingerprint", "notes", "reviewer", "checked_at"]
        }
    store_plan(c, pid, old)
    production = c.app.state.production
    assert production.validate(pid, old, for_restore=True)
    with pytest.raises(ValueError):
        production.validate(pid, old)
    state = get(c, pid)
    assert all(
        s["continuity_check"]["status"] == "stale" and s["continuity_check"]["basis"] is None
        for s in state["plan"]["shots"]
    )
    response = save(c, pid, old)
    assert response.status_code == 200, response.text
    assert all(s["continuity_check"]["status"] == "stale" for s in response.json()["plan"]["shots"])
    assert all(t["blocked"] for t in c.get(f"/api/projects/{pid}/production/tasks").json()["tasks"])
    assert (
        action(c, pid, "apply", reader_revision=c.app.state.reader.load(pid)[0]).status_code == 400
    )


@pytest.mark.parametrize(
    "invalid",
    ["anchor", "actor", "image", "basis_actor", "basis_image", "fingerprint", "paired_hash"],
)
def test_restore_keeps_stale_checks_but_rejects_invalid_structure(scene, invalid):
    c, pid, plan, _ = scene
    reviewed(c, pid, plan)
    restored = get(c, pid)["plan"]
    shot = restored["shots"][0]
    if invalid == "anchor":
        shot["after_byte"] -= 1
    elif invalid == "actor":
        shot["actors"] = [{"character_id": "missing"}]
    elif invalid == "image":
        shot["image_asset_id"] = "missing"
    elif invalid == "basis_actor":
        shot["continuity_check"]["basis"]["character_references"] = [{"character_id": "missing"}]
    elif invalid == "basis_image":
        shot["continuity_check"]["basis"]["images"][0]["asset_id"] = "missing"
    elif invalid == "fingerprint":
        shot["continuity_check"]["fingerprint"] = "malformed"
    else:
        shot["continuity_check"]["basis"]["character_references"] = [
            {"character_id": "missing", "figure_asset_id": "asset"}
        ]
    with pytest.raises(ValueError):
        c.app.state.production.validate(pid, restored, for_restore=True)


def test_restore_allows_rejected_assets_and_checks_without_reviving_them(scene):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    plan["shots"][0]["actors"] = [{"character_id": cid}]
    reviewed(c, pid, plan)
    old = get(c, pid)["plan"]
    reader = c.app.state.reader
    reader.accept(pid, reader.load(pid)[0], plan["shots"][0]["image_asset_id"], "rejected")
    review = reader.review
    review.character(
        pid, review.state(pid)["revision"], "她", [], "合成人物", cid, status="rejected"
    )
    assert c.app.state.production.validate(pid, old, for_restore=True)
    with pytest.raises(ValueError):
        c.app.state.production.validate(pid, old)
    assert all(s["continuity_check"]["status"] == "stale" for s in get(c, pid)["plan"]["shots"])
    # Revocation remains available even when the old image is no longer accepted.
    assert (
        action(
            c,
            pid,
            "shot-0/continuity-check",
            decision="revoked",
            notes="图片及人物已拒绝，正式撤销之前的检查。",
        ).status_code
        == 200
    )


def test_validate_applied_checks_only_actual_plates_and_required_predecessors(scene):
    c, pid, plan, _ = scene
    reviewed(c, pid, plan)
    production = c.app.state.production
    assert (
        action(c, pid, "apply", reader_revision=c.app.state.reader.load(pid)[0]).status_code == 200
    )
    config = c.app.state.reader.load(pid)[1]
    assert production.validate_applied(pid, config) == get(c, pid)["revision"]
    for field, value in [("image_asset_id", "missing"), ("after_byte", 1), ("id", "plan-missing")]:
        bad = copy.deepcopy(config)
        bad["illustrations"][0][field] = value
        with pytest.raises(ValueError):
            production.validate_applied(pid, bad)
    assert (
        action(
            c,
            pid,
            "shot-1/continuity-check",
            decision="rejected",
            notes="中间镜头未通过，请重新核对灯的位置。",
        ).status_code
        == 200
    )
    with pytest.raises(ValueError):
        production.validate_applied(pid, config)
    config["illustrations"] = config["illustrations"][:1]
    assert production.validate_applied(pid, config) == get(c, pid)["revision"]
    current = get(c, pid)["plan"]
    current["shots"][2]["after_byte"] = 1  # Simulate an unrelated malformed imported draft.
    current["shots"][2].update(status="draft", continuity_check=None)
    current["shots"][2]["continuity"].update(scene_id=None, states=[])
    store_plan(c, pid, current)
    assert production.validate_applied(pid, config) == get(c, pid)["revision"]
    config["illustrations"] = []
    assert production.validate_applied(pid, config) == get(c, pid)["revision"]


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
        json={
            "project_id": pid,
            "base_plan_revision": state["revision"],
            **{k: state[k] for k in ["source_sha256", "plan"]},
        },
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
