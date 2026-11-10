"""Production checks, portable drafts and final reader delivery must agree."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal import reader_export
from storygal.app import create_app
from storygal.delivery import REVIEW_CHECKS


def request(client, prefix, action, **data):
    state = client.get(prefix + "/production").json()
    response = client.post(
        prefix + "/production/" + action, json={"revision": state["revision"], **data}
    )
    assert response.status_code == 200, response.text
    return response.json()


def check_all(client, prefix):
    plan = client.get(prefix + "/production").json()["plan"]
    for shot in plan["shots"]:
        request(
            client,
            prefix,
            shot["id"] + "/continuity-check",
            decision="passed",
            notes="合成回归检查：固定灯位及人物参考已核对。",
            reviewer="assistant",
        )
    request(
        client, prefix, "apply", reader_revision=client.get(prefix + "/reader").json()["revision"]
    )


@pytest.fixture
def compiled(tmp_path):
    client = TestClient(create_app(tmp_path / "original"))
    raw = "章节\n灯在门上。\n她等候回应。".encode()
    project = client.post(
        "/api/projects", files={"file": ("synthetic.txt", raw)}, data={"rights_status": "owned"}
    ).json()
    pid, prefix = project["id"], "/api/projects/" + project["id"]
    reader, review = client.app.state.reader, client.app.state.review
    image = io.BytesIO()
    Image.new("RGB", (80, 45), "tan").save(image, "PNG")
    asset = reader.upload(pid, 0, image.getvalue(), "scene", "synthetic regression fixture")
    reader.accept(pid, reader.load(pid)[0], asset["id"], "accepted")
    char = review.character(pid, review.state(pid)["revision"], "她", [], "合成人物")
    portrait = review.upload_asset(
        pid,
        review.state(pid)["revision"],
        char["id"],
        image.getvalue(),
        "reference_and_figure",
        "synthetic regression fixture",
    )
    review.accept_asset(pid, review.state(pid)["revision"], portrait["id"], "accepted", True)
    revision, config = reader.load(pid)
    config["scenes"] = [
        {
            "id": "opening",
            "title": "门前",
            "start_byte": 0,
            "asset_id": asset["id"],
            "character_ids": [],
        }
    ]
    reader.save(pid, revision, config)
    plan = {
        "scenes": [
            {
                "id": "door",
                "title": "门前",
                "layout": "灯固定在门上",
                "reference_asset_id": asset["id"],
                "objects": [{"id": "lamp", "name": "灯", "kind": "fixed", "home": "门上"}],
            }
        ],
        "shots": [
            {
                "id": f"shot-{index}",
                "title": f"镜头{index}",
                "after_byte": block["byte_end"],
                "moment": block["text"],
                "evidence": block["text"],
                "framing": "固定机位",
                "avoid": "不提前画出回应",
                "image_asset_id": asset["id"],
                "actors": [{"character_id": char["id"]}],
                "continuity": {
                    "scene_id": "door",
                    "camera": "平视",
                    "changes": "只改变人物动作",
                    "states": [{"object_id": "lamp", "visibility": "visible", "position": "门上"}],
                },
            }
            for index, block in enumerate(reader.blocks(pid)[1:])
        ],
    }
    state = client.get(prefix + "/production").json()
    response = client.put(
        prefix + "/production",
        json={
            "revision": state["revision"],
            "source_sha256": state["source_sha256"],
            "plan": plan,
        },
    )
    assert response.status_code == 200, response.text
    for shot in plan["shots"]:
        request(client, prefix, shot["id"] + "/approve")
    check_all(client, prefix)
    return client, prefix, raw, char["id"]


def export(client, prefix):
    response = client.post(prefix + "/reader/exports")
    assert response.status_code == 202, response.text
    return next(
        j for j in client.get(prefix + "/jobs").json() if j["id"] == response.json()["job_id"]
    )


def migrate(client, prefix, tmp_path):
    archive = client.get(prefix + "/bundle")
    assert archive.status_code == 200, archive.text
    restored = TestClient(create_app(tmp_path))
    response = restored.post("/api/project-bundles", files={"file": ("draft.zip", archive.content)})
    assert response.status_code == 201, response.text
    return restored, "/api/projects/" + response.json()["id"]


def test_checked_identity_survives_migration_and_exports(compiled, tmp_path):
    client, prefix, raw, _ = compiled
    restored, target = migrate(client, prefix, tmp_path / "restored")
    assert restored.get(target + "/source").content == raw
    assert restored.get(target + "/delivery").json()["ready"]
    job = export(restored, target)
    assert job["state"] == "completed", job
    with zipfile.ZipFile(
        io.BytesIO(restored.get(job["result"]["download_url"]).content)
    ) as archive:
        assert archive.read("storygal-source/original.txt") == raw
        data = json.loads(archive.read("reader.json"))
        assert "production_revision" in data["versions"]
        assert "continuity_check" not in data


def test_rejected_applied_frame_blocks_delivery_until_rechecked(compiled, tmp_path):
    client, prefix, raw, _ = compiled
    old = export(client, prefix)
    assert old["state"] == "completed", old
    request(
        client,
        prefix,
        "shot-0/continuity-check",
        decision="rejected",
        notes="复审发现灯的位置错误，必须重新检查。",
    )
    readiness = client.get(prefix + "/delivery").json()
    assert not readiness["ready"] and readiness["stale"]
    assert export(client, prefix)["state"] == "failed"
    approval = client.post(
        prefix + f"/exports/{old['id']}/review",
        json={
            "checks": {key: True for key in REVIEW_CHECKS},
            "notes": "synthetic fixture",
        },
    )
    assert approval.status_code == 409
    assert client.get(old["result"]["download_url"]).status_code == 200
    restored, target = migrate(client, prefix, tmp_path / "rejected")
    assert restored.get(target + "/source").content == raw
    assert not restored.get(target + "/delivery").json()["ready"]
    assert export(restored, target)["state"] == "failed"
    check_all(restored, target)
    assert export(restored, target)["state"] == "completed"


def test_reference_change_survives_migration_as_stale(compiled, tmp_path):
    client, prefix, _, cid = compiled
    pid = prefix.rsplit("/", 1)[1]
    review = client.app.state.review
    image = io.BytesIO()
    Image.new("RGB", (80, 45), "blue").save(image, "PNG")
    asset = review.upload_asset(
        pid,
        review.state(pid)["revision"],
        cid,
        image.getvalue(),
        "reference_and_figure",
        "synthetic",
    )
    review.accept_asset(pid, review.state(pid)["revision"], asset["id"], "accepted", True)
    restored, target = migrate(client, prefix, tmp_path / "changed")
    assert not restored.get(target + "/delivery").json()["ready"]
    assert export(restored, target)["state"] == "failed"
    check_all(restored, target)
    assert export(restored, target)["state"] == "completed"


def test_recheck_change_during_reader_export_is_not_published(compiled, monkeypatch):
    client, prefix, _, _ = compiled
    original = reader_export.copy_verified
    changed = False

    def copy_and_reject(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            request(
                client,
                prefix,
                "shot-0/continuity-check",
                decision="rejected",
                notes="导出期间复审不通过，需要修复此镜头。",
            )
        return result

    monkeypatch.setattr(reader_export, "copy_verified", copy_and_reject)
    job = export(client, prefix)
    assert job["state"] == "failed", job
    assert "制作状态" in job["error"]
    directory = client.app.state.store.project_dir(prefix.rsplit("/", 1)[1]) / "exports"
    assert not list(directory.iterdir())


@pytest.mark.parametrize("merge_count", [1, 2])
def test_merged_character_and_historical_figure_restore_without_approval(
    compiled, tmp_path, merge_count
):
    client, prefix, raw, cid = compiled
    pid = prefix.rsplit("/", 1)[1]
    reader, review = client.app.state.reader, client.app.state.review
    revision, config = reader.load(pid)
    scene = config["scenes"][0]
    figure = next(c for c in review.state(pid)["characters"] if c["id"] == cid)["active_figure_id"]
    config["presentations"] = [
        {
            "id": "portrait",
            "scene_id": scene["id"],
            "start_byte": 0,
            "kind": "dialogue",
            "image_asset_id": scene["asset_id"],
            "place_label": "门前",
            "time_label": "",
            "cast": [{"character_id": cid, "figure_asset_id": figure, "slot": "left"}],
        }
    ]
    reader.save(pid, revision, config)
    current = cid
    for index in range(merge_count):
        target = review.character(pid, review.state(pid)["revision"], f"合并目标{index}", [], "")
        review.merge(pid, review.state(pid)["revision"], current, target["id"])
        current = target["id"]
    state = client.get(prefix + "/production").json()
    assert all(s["continuity_check"]["status"] == "stale" for s in state["plan"]["shots"])
    restored, dest = migrate(client, prefix, tmp_path / "merged")
    assert restored.get(dest + "/source").content == raw
    assert (
        restored.get(dest + "/reader").json()["config"]["presentations"] == config["presentations"]
    )
    checks = restored.get(dest + "/production").json()["plan"]["shots"]
    assert all(s["continuity_check"]["status"] == "stale" for s in checks)
    assert checks[0]["continuity_check"]["basis"]["character_references"][0]["character_id"] == cid
    assert export(restored, dest)["state"] == "failed"


@pytest.mark.parametrize("invalid", ["missing", "cycle", "unrelated_figure"])
def test_invalid_merge_history_still_rejects_restore(compiled, tmp_path, invalid):
    from storygal.text import sha256

    client, prefix, _, cid = compiled
    with zipfile.ZipFile(io.BytesIO(client.get(prefix + "/bundle").content)) as z:
        files = {n: z.read(n) for n in z.namelist() if n != "manifest.json"}
    doc = json.loads(files["project.json"])
    char = next(c for c in doc["records"]["characters"] if c["id"] == cid)
    if invalid == "unrelated_figure":
        unrelated = dict(char, id="unrelated", active_figure_id=None)
        doc["records"]["characters"].append(unrelated)
        char["active_figure_id"] = None
        doc["records"]["assets"][0]["character_id"] = unrelated["id"]
    else:
        char.update(
            status="merged",
            merged_into=cid if invalid == "cycle" else "missing",
            active_figure_id=None,
        )
    files["project.json"] = json.dumps(doc).encode()
    files["manifest.json"] = json.dumps(
        {
            "format": "storygal-project-inventory",
            "version": 1,
            "files": {n: sha256(v) for n, v in files.items()},
        }
    ).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    restored = TestClient(create_app(tmp_path / "invalid"))
    response = restored.post(
        "/api/project-bundles", files={"file": ("invalid.zip", out.getvalue())}
    )
    assert response.status_code == 400, response.text
    assert restored.get("/api/projects").json() == []
