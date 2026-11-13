"""Selected identity references and explicit reuse are portable, dependency-bound inputs."""

import copy
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_continuity import (
    action,
    add_character_reference,
    add_reference,
    get,
    no_model_or_local_secrets,  # noqa: F401 -- shared fixture
    reviewed,
    save,
    store_plan,
)
from test_continuity import (
    scene as scene_fixture,
)

from storygal import continuity as cont
from storygal.app import create_app
from storygal.production import Plan
from storygal.text import sha256

scene = scene_fixture


def identity(c, pid, cid, color="green", status="accepted", kind="reference"):
    review = c.app.state.reader.review
    image = io.BytesIO()
    Image.new("RGB", (20, 30), color).save(image, "PNG")
    asset = review.upload_asset(
        pid, review.state(pid)["revision"], cid, image.getvalue(), kind, "synthetic identity"
    )
    review.accept_asset(pid, review.state(pid)["revision"], asset["id"], status, False)
    return asset


def tasks(c, pid):
    response = c.get(f"/api/projects/{pid}/production/tasks")
    assert response.status_code == 200, response.text
    return response.json()["tasks"]


def migrate(c, pid, destination):
    bundle = c.get(f"/api/projects/{pid}/bundle")
    assert bundle.status_code == 200, bundle.text
    other = TestClient(create_app(destination))
    response = other.post("/api/project-bundles", files={"file": ("project.zip", bundle.content)})
    assert response.status_code == 201, response.text
    return other, response.json()["id"]


def review_status_transaction(c, pid, cid, aid, status):
    """Use the real asset review transaction, including its persisted invalidation hook."""
    review = c.app.state.reader.review
    assert next(a for a in review.state(pid)["assets"] if a["id"] == aid)["character_id"] == cid
    review.accept_asset(pid, review.state(pid)["revision"], aid, status, False)


def scene_image(c, pid, color="red"):
    reader = c.app.state.reader
    image = io.BytesIO()
    Image.new("RGB", (80, 45), color).save(image, "PNG")
    return reader.upload(pid, reader.load(pid)[0], image.getvalue(), "scene", "test scene image")


def stored_production(c, pid):
    with c.app.state.store.db() as db:
        row = db.execute(
            "SELECT revision,data FROM production_states WHERE project_id=?", (pid,)
        ).fetchone()
    return row[0], json.loads(row[1])


def test_identity_only_reference_binds_task_and_check_without_display_change(scene, tmp_path):
    c, pid, plan, raw = scene
    cid, display = add_character_reference(c, pid)
    chosen = identity(c, pid, cid)
    plan["shots"][0]["actors"] = [{"character_id": cid, "reference_asset_id": chosen["id"]}]
    reviewed(c, pid, plan)
    expected = {
        "character_id": cid,
        "figure_asset_id": chosen["id"],
        "sha256": chosen["sha256"],
    }
    task = tasks(c, pid)[0]
    assert task["references"] == [expected]
    assert task["image_references"][-1] == {
        "asset_id": chosen["id"],
        "role": "character identity",
        "character_id": cid,
        "sha256": chosen["sha256"],
    }
    assert display["id"] not in json.dumps(task)
    state = get(c, pid)
    assert state["plan"]["shots"][0]["continuity_check"]["basis"]["character_references"] == [
        expected
    ]
    assert (
        c.app.state.reader.review.state(pid)["characters"][0]["active_figure_id"] == display["id"]
    )
    other, restored_pid = migrate(c, pid, tmp_path / "restored")
    assert get(other, restored_pid)["plan"] == state["plan"]
    assert tasks(other, restored_pid)[0]["references"] == [expected]
    assert other.get(f"/api/projects/{restored_pid}/source").content == raw


def test_identity_reference_works_without_any_display_figure(scene):
    c, pid, plan, _ = scene
    review = c.app.state.reader.review
    char = review.character(pid, review.state(pid)["revision"], "她", [], "合成人物")
    chosen = identity(c, pid, char["id"])
    plan["shots"][0]["actors"] = [{"character_id": char["id"], "reference_asset_id": chosen["id"]}]
    reviewed(c, pid, plan)
    assert tasks(c, pid)[0]["references"][0]["figure_asset_id"] == chosen["id"]
    assert review.state(pid)["characters"][0]["active_figure_id"] is None


def test_display_switch_only_invalidates_shots_using_default_reference(scene):
    c, pid, plan, _ = scene
    cid, original = add_character_reference(c, pid)
    # Lock even the displayed image explicitly: changing display must leave this choice intact.
    plan["shots"][0]["actors"] = [{"character_id": cid, "reference_asset_id": original["id"]}]
    plan["shots"][1]["actors"] = [{"character_id": cid}]
    reviewed(c, pid, plan)
    before = get(c, pid)
    add_reference(c, pid, cid, "red")
    review = c.app.state.reader.review
    review.accept_asset(pid, review.state(pid)["revision"], original["id"], "accepted", True)
    after = get(c, pid)
    assert after["revision"] == before["revision"] + 2
    assert [s["continuity_check"]["status"] for s in after["plan"]["shots"]] == [
        "passed",
        "stale",
        "stale",
    ]
    assert tasks(c, pid)[0]["references"][0]["figure_asset_id"] == original["id"]


def test_explicit_reference_selection_a_b_a_never_restores_check(scene, tmp_path):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    a, b = identity(c, pid, cid), identity(c, pid, cid, "red")
    plan["shots"][1]["actors"] = [{"character_id": cid, "reference_asset_id": a["id"]}]
    reviewed(c, pid, plan)
    old = get(c, pid)
    changed = copy.deepcopy(old["plan"])
    changed["shots"][1]["actors"][0]["reference_asset_id"] = b["id"]
    assert save(c, pid, changed).status_code == 200
    # A fresh write of the old, fully checked plan cannot reinstate its old checks.
    returned = save(c, pid, old["plan"])
    assert returned.status_code == 200, returned.text
    shots = returned.json()["plan"]["shots"]
    assert shots[0]["continuity_check"]["status"] == "passed"
    assert all(s["continuity_check"] is None for s in shots[1:])
    assert tasks(c, pid)[1]["references"][0]["figure_asset_id"] == a["id"]
    other, restored_pid = migrate(c, pid, tmp_path / "selection-return")
    assert get(other, restored_pid)["plan"] == returned.json()["plan"]


def test_reference_status_hook_persists_rejection_even_after_accept_and_migration(scene, tmp_path):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    chosen, unused = identity(c, pid, cid), identity(c, pid, cid, "yellow")
    plan["shots"][1]["actors"] = [{"character_id": cid, "reference_asset_id": chosen["id"]}]
    reviewed(c, pid, plan)
    before = get(c, pid)
    review_status_transaction(c, pid, cid, unused["id"], "rejected")
    assert get(c, pid) == before
    review_status_transaction(c, pid, cid, chosen["id"], "rejected")
    # No intervening GET: invalidation must be stored by the transaction itself.
    review_status_transaction(c, pid, cid, chosen["id"], "accepted")
    changed = get(c, pid)
    assert changed["revision"] == before["revision"] + 2
    assert [s["continuity_check"]["status"] for s in changed["plan"]["shots"]] == [
        "passed",
        "stale",
        "stale",
    ]
    assert tasks(c, pid)[2]["blocked"]
    other, restored_pid = migrate(c, pid, tmp_path / "status-return")
    assert get(other, restored_pid)["plan"] == changed["plan"]


@pytest.mark.parametrize("usage", ["frame", "master"])
def test_scene_image_rejection_persists_through_reacceptance(scene, tmp_path, usage):
    c, pid, plan, _ = scene
    target = scene_image(c, pid)["id"]
    if usage == "frame":
        plan["shots"][1]["image_asset_id"] = target
        expected = ["passed", "stale", "stale"]
        unrelated = 0
    else:
        plan["scenes"].append({**copy.deepcopy(plan["scenes"][0]), "id": "other"})
        plan["shots"][2]["continuity"]["scene_id"] = "other"
        plan["scenes"][0]["reference_asset_id"] = target
        expected = ["stale", "stale", "passed"]
        unrelated = 2
    reviewed(c, pid, plan)
    before = get(c, pid)
    reader = c.app.state.reader
    for status, bump in [("accepted", 0), ("rejected", 1), ("accepted", 2)]:
        reader.accept(pid, reader.load(pid)[0], target, status)
        revision, stored = stored_production(c, pid)
        assert revision == before["revision"] + bump
        checks = [s["continuity_check"] for s in stored["shots"]]
        assert [check["status"] for check in checks] == (expected if bump else ["passed"] * 3)
        assert checks[unrelated] == before["plan"]["shots"][unrelated]["continuity_check"]
    assert [task["blocked"] for task in tasks(c, pid)] == [s == "stale" for s in expected]
    assert action(c, pid, "apply", reader_revision=reader.load(pid)[0]).status_code == 400
    other, restored_pid = migrate(c, pid, tmp_path / "reaccepted-scene")
    assert get(other, restored_pid)["plan"] == stored


@pytest.mark.parametrize("excluded", ["candidate", "rejected"])
def test_character_exclusion_persists_through_reconfirmation(scene, excluded):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    chosen = identity(c, pid, cid)
    plan["shots"][1]["actors"] = [{"character_id": cid, "reference_asset_id": chosen["id"]}]
    reviewed(c, pid, plan)
    before = get(c, pid)
    review = c.app.state.reader.review
    for status, bump in [("confirmed", 0), (excluded, 1), ("confirmed", 2)]:
        review.character(pid, review.state(pid)["revision"], "她", [], "更新描述", cid, status)
        revision, stored = stored_production(c, pid)
        assert revision == before["revision"] + bump
        checks = [s["continuity_check"] for s in stored["shots"]]
        assert [check["status"] for check in checks] == (
            ["passed", "stale", "stale"] if bump else ["passed"] * 3
        )
        assert checks[0] == before["plan"]["shots"][0]["continuity_check"]
    assert [task["blocked"] for task in tasks(c, pid)] == [False, True, True]


def test_same_character_may_use_different_references_in_a_checked_sequence(scene, tmp_path):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    a, b = identity(c, pid, cid), identity(c, pid, cid, "red")
    for shot, selected in zip(plan["shots"], [a, b, a], strict=True):
        shot["actors"] = [{"character_id": cid, "reference_asset_id": selected["id"]}]
    reviewed(c, pid, plan)
    for shot, task, selected in zip(get(c, pid)["plan"]["shots"], tasks(c, pid), [a, b, a]):
        refs = shot["continuity_check"]["basis"]["character_references"]
        assert refs == task["references"]
        assert refs[0]["figure_asset_id"] == selected["id"]
        assert refs[0]["sha256"] == selected["sha256"]
    other, other_pid = migrate(c, pid, tmp_path / "multiple-references")
    assert get(other, other_pid)["plan"] == get(c, pid)["plan"]
    review_status_transaction(c, pid, cid, b["id"], "rejected")
    assert [s["continuity_check"]["status"] for s in get(c, pid)["plan"]["shots"]] == [
        "passed",
        "stale",
        "stale",
    ]


def test_predecessor_hash_remains_protected_when_later_shot_uses_another_reference(scene):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    a, b = identity(c, pid, cid), identity(c, pid, cid, "red")
    for shot, selected in zip(plan["shots"], [a, b, b], strict=True):
        shot["actors"] = [{"character_id": cid, "reference_asset_id": selected["id"]}]
    reviewed(c, pid, plan)
    review = c.app.state.reader.review
    with review.store.db() as db:
        asset = review.item(db, "assets", pid, a["id"])
        asset["sha256"] = "0" * 64
        review.put(db, "assets", pid, asset)
    current = get(c, pid)["plan"]
    assert all(s["continuity_check"]["status"] == "stale" for s in current["shots"])
    assert (
        current["shots"][1]["continuity_check"]["basis"]["character_references"][0][
            "figure_asset_id"
        ]
        == b["id"]
    )
    assert all(t["blocked"] for t in tasks(c, pid))


@pytest.mark.parametrize("case", ["missing", "foreign", "pending", "rejected", "candidate"])
def test_invalid_explicit_references_are_rejected_without_altering_plan(scene, case):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    chosen = identity(c, pid, cid, status=case if case in {"pending", "rejected"} else "accepted")
    aid = chosen["id"]
    if case == "missing":
        aid = "missing-asset"
    elif case == "foreign":
        other_id, _ = add_character_reference(c, pid, "旁人", "yellow")
        aid = identity(c, pid, other_id)["id"]
    elif case == "candidate":
        review = c.app.state.reader.review
        review.character(pid, review.state(pid)["revision"], "她", [], "候选人物", cid, "candidate")
    plan["shots"][0]["actors"] = [{"character_id": cid, "reference_asset_id": aid}]
    before = get(c, pid)
    response = save(c, pid, plan)
    assert response.status_code == 400, response.text
    assert get(c, pid) == before


def test_restore_rejected_reference_preserves_stale_checks_but_requires_repair(scene, tmp_path):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    chosen = identity(c, pid, cid)
    plan["shots"][0]["actors"] = [{"character_id": cid, "reference_asset_id": chosen["id"]}]
    reviewed(c, pid, plan)
    review_status_transaction(c, pid, cid, chosen["id"], "rejected")
    other, restored_pid = migrate(c, pid, tmp_path / "rejected-reference")
    shot = get(other, restored_pid)["plan"]["shots"][0]
    assert shot["actors"][0]["reference_asset_id"] == chosen["id"]
    assert shot["continuity_check"]["status"] == "stale"
    assert tasks(other, restored_pid)[0]["blocked"]
    assert action(other, restored_pid, "shot-0/approve").status_code == 400


def test_merge_of_actor_with_explicit_reference_remains_restorable(scene, tmp_path):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    target, _ = add_character_reference(c, pid, "另一人", "red")
    chosen = identity(c, pid, cid)
    plan["shots"][0]["actors"] = [{"character_id": cid, "reference_asset_id": chosen["id"]}]
    reviewed(c, pid, plan)
    review = c.app.state.reader.review
    review.merge(pid, review.state(pid)["revision"], cid, target)
    other, restored_pid = migrate(c, pid, tmp_path / "merged-reference")
    shot = get(other, restored_pid)["plan"]["shots"][0]
    assert shot["actors"][0]["character_id"] == cid
    assert shot["continuity_check"]["status"] == "stale"
    assert tasks(other, restored_pid)[0]["blocked"]


@pytest.mark.parametrize("previously_checked", [True, False])
def test_concurrent_reference_a_b_a_cannot_commit_passing_check(
    scene, monkeypatch, previously_checked
):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    chosen = identity(c, pid, cid)
    plan["shots"][0]["actors"] = [{"character_id": cid, "reference_asset_id": chosen["id"]}]
    if previously_checked:
        reviewed(c, pid, plan)
    else:
        assert save(c, pid, plan).status_code == 200
        assert action(c, pid, "shot-0/approve").status_code == 200
    production = c.app.state.production
    original_validate = production.validate

    def change_after_validation(*args, **kwargs):
        result = original_validate(*args, **kwargs)
        review_status_transaction(c, pid, cid, chosen["id"], "rejected")
        review_status_transaction(c, pid, cid, chosen["id"], "accepted")
        return result

    monkeypatch.setattr(production, "validate", change_after_validation)
    response = action(c, pid, "shot-0/continuity-check", notes="并发重新检查不能覆盖参考撤销记录。")
    assert response.status_code == 409, response.text
    check = get(c, pid)["plan"]["shots"][0]["continuity_check"]
    assert (check["status"] == "stale") if previously_checked else (check is None)


def test_reference_hash_changes_are_detected_at_commit(scene, monkeypatch):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    chosen = identity(c, pid, cid)
    plan["shots"][0]["actors"] = [{"character_id": cid, "reference_asset_id": chosen["id"]}]
    assert save(c, pid, plan).status_code == 200
    assert action(c, pid, "shot-0/approve").status_code == 200
    production = c.app.state.production
    original_validate = production.validate

    def change_after_validation(*args, **kwargs):
        result = original_validate(*args, **kwargs)
        with production.store.db() as db:
            asset = production.reader.review.item(db, "assets", pid, chosen["id"])
            asset["sha256"] = "0" * 64
            production.reader.review.put(db, "assets", pid, asset)
        return result

    monkeypatch.setattr(production, "validate", change_after_validation)
    response = action(c, pid, "shot-0/continuity-check", notes="并发时只允许核对过的图片被确认。")
    assert response.status_code == 409, response.text
    assert get(c, pid)["plan"]["shots"][0]["continuity_check"] is None


def test_scene_rejection_and_reacceptance_conflicts_with_first_in_flight_check(scene, monkeypatch):
    c, pid, plan, _ = scene
    target = plan["shots"][0]["image_asset_id"]
    assert save(c, pid, plan).status_code == 200
    assert action(c, pid, "shot-0/approve").status_code == 200
    production = c.app.state.production
    original_validate = production.validate
    reader = c.app.state.reader

    def change_after_validation(*args, **kwargs):
        result = original_validate(*args, **kwargs)
        for status in ("rejected", "accepted"):
            reader.accept(pid, reader.load(pid)[0], target, status)
        return result

    monkeypatch.setattr(production, "validate", change_after_validation)
    response = action(c, pid, "shot-0/continuity-check", notes="并发时成图被拒绝后再次接受。")
    assert response.status_code == 409, response.text
    assert get(c, pid)["plan"]["shots"][0]["continuity_check"] is None


def test_optional_selectors_keep_existing_fingerprints_and_checks_compatible(scene):
    c, pid, plan, _ = scene
    cid, _ = add_character_reference(c, pid)
    plan["shots"][0]["actors"] = [{"character_id": cid}]
    reviewed(c, pid, plan)
    original = get(c, pid)["plan"]
    legacy = copy.deepcopy(original)
    for shot in legacy["shots"]:
        for actor in shot["actors"]:
            actor.pop("reference_asset_id")
        shot["continuity"].pop("reuse_asset_id")
    first = legacy["shots"][0]
    old_data = {
        "style": legacy["style"],
        "scene": legacy["scenes"][0],
        "shots": [{k: v for k, v in first.items() if k not in {"status", "continuity_check"}}],
    }
    old_fingerprint = sha256(json.dumps(old_data, ensure_ascii=False, sort_keys=True).encode())
    assert old_fingerprint == first["continuity_check"]["fingerprint"]
    assert cont.fingerprint(Plan.model_validate(legacy).model_dump(), original["shots"][0]) == (
        old_fingerprint
    )
    store_plan(c, pid, legacy)
    assert get(c, pid)["plan"] == original


@pytest.mark.parametrize("method", ["edit", "new_view"])
def test_switching_from_reuse_allows_replacing_rejected_target(scene, method):
    c, pid, plan, _ = scene
    target = scene_image(c, pid)["id"]
    shot = plan["shots"][0]
    replacement = shot["image_asset_id"]
    shot["image_asset_id"] = target
    shot["continuity"].update(method="reuse", reuse_asset_id=target)
    reviewed(c, pid, plan)
    reader = c.app.state.reader
    reader.accept(pid, reader.load(pid)[0], target, "rejected")
    # A legacy client may leave the old selector in its replacement request.
    shot["continuity"]["method"] = method
    shot["image_asset_id"] = replacement
    response = save(c, pid, plan)
    assert response.status_code == 200, response.text
    saved = response.json()["plan"]["shots"][0]
    assert saved["image_asset_id"] == replacement
    assert saved["continuity"]["reuse_asset_id"] is None
    assert saved["status"] == "draft" and saved["continuity_check"] is None
    task = tasks(c, pid)[0]
    assert task["action"] == method and task["target_asset_id"] is None and not task["blocked"]
    assert target not in json.dumps(task)


def test_legacy_inactive_reuse_does_not_change_checked_evidence(scene, tmp_path):
    c, pid, plan, _ = scene
    target = scene_image(c, pid)["id"]
    reviewed(c, pid, plan)
    before = get(c, pid)
    legacy = copy.deepcopy(before["plan"])
    legacy["shots"][1]["continuity"]["reuse_asset_id"] = target
    for shot in legacy["shots"][1:]:
        # Reproduce the old hash, which included every non-null reuse selector.
        data = {"style": legacy["style"], "scene": legacy["scenes"][0], "shots": []}
        for dependency in cont.sequence(legacy, shot):
            content = {
                k: v for k, v in dependency.items() if k not in {"status", "continuity_check"}
            }
            content["continuity"] = {
                k: v for k, v in content["continuity"].items() if v is not None
            }
            data["shots"].append(content)
        shot["continuity_check"]["fingerprint"] = sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
        )
    store_plan(c, pid, legacy)
    reader = c.app.state.reader
    reader.accept(pid, reader.load(pid)[0], target, "rejected")
    assert get(c, pid) == before
    assert all(target not in json.dumps(task) and not task["blocked"] for task in tasks(c, pid))
    other, restored_pid = migrate(c, pid, tmp_path / "inactive-reuse")
    assert get(other, restored_pid)["plan"] == before["plan"]
    saved = save(c, pid, legacy)
    assert saved.status_code == 200, saved.text
    assert stored_production(c, pid)[1] == before["plan"]


@pytest.mark.parametrize("with_scene", [True, False])
@pytest.mark.parametrize("explicit", [True, False])
def test_reuse_uses_the_selected_result_not_the_master(scene, with_scene, explicit, monkeypatch):
    c, pid, plan, _ = scene
    reader = c.app.state.reader
    image = io.BytesIO()
    Image.new("RGB", (80, 45), "red").save(image, "PNG")
    result = reader.upload(pid, reader.load(pid)[0], image.getvalue(), "scene", "reuse result")
    plan["shots"] = plan["shots"][:1]
    shot = plan["shots"][0]
    shot["image_asset_id"] = result["id"]
    shot["continuity"]["method"] = "reuse"
    if explicit:
        shot["continuity"]["reuse_asset_id"] = result["id"]
    if not with_scene:
        shot["continuity"].update(scene_id=None, states=[])
    assert save(c, pid, plan).status_code == 200

    def no_generation_prompt(*_args, **_kwargs):
        pytest.fail("Reuse must never render a generation or editing template")

    monkeypatch.setattr("storygal.prompts.render", no_generation_prompt)
    task = tasks(c, pid)[0]
    assert task["action"] == "reuse" and not task["blocked"]
    assert task["template"] is None
    assert task["target_asset_id"] == result["id"]
    assert task["target_sha256"] == result["sha256"]
    assert task["image_references"][0] == {
        "asset_id": result["id"],
        "sha256": result["sha256"],
        "role": "reuse target",
    }
    assert "不调用生图或编辑工具" in task["prompt"]
    assert "复用现有母版" not in task["prompt"]
    assert action(c, pid, "shot-0/approve").status_code == 200


@pytest.mark.parametrize("with_scene", [True, False])
def test_reuse_missing_target_is_blocked_even_if_scene_has_master(scene, with_scene, monkeypatch):
    c, pid, plan, _ = scene
    plan["shots"] = plan["shots"][:1]
    shot = plan["shots"][0]
    shot["image_asset_id"] = None
    shot["continuity"]["method"] = "reuse"
    if not with_scene:
        shot["continuity"].update(scene_id=None, states=[])
    assert save(c, pid, plan).status_code == 200

    def no_generation_prompt(*_args, **_kwargs):
        pytest.fail("Missing reuse target must not fall back to generation")

    monkeypatch.setattr("storygal.prompts.render", no_generation_prompt)
    task = tasks(c, pid)[0]
    assert task["action"] == "reuse" and task["blocked"]
    assert task["template"] is None
    assert task["target_asset_id"] is None and task["target_sha256"] is None
    assert "尚未指定复用成图" in task["blocked_reason"]
    assert action(c, pid, "shot-0/approve").status_code == 400


@pytest.mark.parametrize("invalid", ["missing", "wrong_kind", "rejected"])
def test_reuse_rejects_invalid_target_instead_of_generating(scene, invalid):
    c, pid, plan, _ = scene
    target = plan["shots"][0]["image_asset_id"]
    reader = c.app.state.reader
    if invalid == "missing":
        target = "missing-result"
    elif invalid == "wrong_kind":
        _, ref = add_character_reference(c, pid)
        target = ref["id"]
    else:
        reader.accept(pid, reader.load(pid)[0], target, "rejected")
    plan["shots"][0]["continuity"].update(method="reuse", reuse_asset_id=target)
    assert save(c, pid, plan).status_code == 400
    # Malformed historical state is still safe to inspect: no generation task escapes.
    get(c, pid)
    store_plan(c, pid, Plan.model_validate(plan).model_dump())
    task = tasks(c, pid)[0]
    assert task["action"] == "reuse" and task["blocked"]
    assert task["template"] is None
    assert task["target_sha256"] is None


def test_reuse_target_must_match_applied_image_and_remains_portable(scene, tmp_path):
    c, pid, plan, _ = scene
    reader = c.app.state.reader
    image = io.BytesIO()
    Image.new("RGB", (80, 45), "red").save(image, "PNG")
    target = reader.upload(pid, reader.load(pid)[0], image.getvalue(), "scene", "reuse result")
    plan["shots"] = plan["shots"][:1]
    plan["shots"][0]["continuity"].update(method="reuse", reuse_asset_id=target["id"])
    assert save(c, pid, plan).status_code == 200
    assert tasks(c, pid)[0]["blocked"]
    assert action(c, pid, "shot-0/approve").status_code == 400
    plan["shots"][0]["image_asset_id"] = target["id"]
    reviewed(c, pid, plan)
    assert action(c, pid, "apply", reader_revision=reader.load(pid)[0]).status_code == 200
    assert reader.load(pid)[1]["illustrations"][0]["image_asset_id"] == target["id"]
    basis = get(c, pid)["plan"]["shots"][0]["continuity_check"]["basis"]
    assert {"asset_id": target["id"], "sha256": target["sha256"]} in basis["images"]
    other, restored_pid = migrate(c, pid, tmp_path / "reuse")
    assert get(other, restored_pid)["plan"] == get(c, pid)["plan"]
    assert tasks(other, restored_pid)[0]["target_asset_id"] == target["id"]


def test_explicit_target_can_be_assigned_before_result_is_filled(scene):
    c, pid, plan, _ = scene
    plan["shots"] = plan["shots"][:1]
    shot = plan["shots"][0]
    target = shot["image_asset_id"]
    shot["continuity"].update(method="reuse", reuse_asset_id=target)
    shot["image_asset_id"] = None
    assert save(c, pid, plan).status_code == 200
    task = tasks(c, pid)[0]
    assert task["action"] == "reuse" and not task["blocked"]
    assert task["target_asset_id"] == target
    assert action(c, pid, "shot-0/approve").status_code == 400
