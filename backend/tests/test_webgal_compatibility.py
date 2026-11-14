"""Reader-specific content must never be silently omitted by compatibility export."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal import exporter
from storygal.app import create_app, webgal_losses
from storygal.delivery import REVIEW_CHECKS


@pytest.fixture
def setup(tmp_path):
    client = TestClient(create_app(tmp_path))
    raw = "第一段，灯还亮着。\n第二段，走廊安静下来。".encode()
    pid = client.post(
        "/api/projects",
        files={"file": ("chapter.txt", raw)},
        data={"rights_status": "owned"},
    ).json()["id"]
    return client, pid, client.app.state.reader, raw


def add_illustration(setup):
    _c, pid, reader, _ = setup
    image = io.BytesIO()
    Image.new("RGB", (24, 24), "white").save(image, "PNG")
    asset = reader.upload(pid, reader.load(pid)[0], image.getvalue(), "scene", "Test fixture")
    reader.accept(pid, reader.load(pid)[0], asset["id"], "accepted")
    revision, config = reader.load(pid)
    # No P6 presentations or map entries: this is the formerly silent-loss case.
    config["illustrations"] = [
        {
            "id": "plate-1",
            "after_byte": reader.blocks(pid)[0]["byte_end"],
            "image_asset_id": asset["id"],
            "title": "走廊",
            "description": "段后的独立插图",
        }
    ]
    reader.save(pid, revision, config)
    return asset


def report(c, pid):
    response = c.get(f"/api/projects/{pid}/exports/compatibility")
    assert response.status_code == 200, response.text
    return response.json()


def export(c, pid, snapshot):
    response = c.post(
        f"/api/projects/{pid}/exports",
        params={"simplified": "true", "reader_revision": snapshot["reader_revision"]},
    )
    assert response.status_code == 202, response.text
    return next(j for j in c.get(f"/api/projects/{pid}/jobs").json() if j["id"] == response.json()["job_id"])


def test_plain_project_is_compatible_and_keeps_existing_export_api(setup):
    c, pid, reader, _ = setup
    snapshot = report(c, pid)
    assert snapshot == {"reader_revision": 0, "compatible": True, "losses": []}
    response = c.post(f"/api/projects/{pid}/exports")
    assert response.status_code == 202, response.text
    job = c.get(f"/api/projects/{pid}/jobs").json()[0]
    assert job["state"] == "completed", job
    assert job["result"]["reader_revision"] == reader.load(pid)[0]


def test_chapter_illustration_alone_blocks_silent_loss_without_starting_job(setup):
    c, pid, _, _ = setup
    add_illustration(setup)
    snapshot = report(c, pid)
    assert not snapshot["compatible"]
    assert [loss["field"] for loss in snapshot["losses"]] == ["illustrations"]
    assert "1 张" in snapshot["losses"][0]["detail"]
    response = c.post(f"/api/projects/{pid}/exports")
    assert response.status_code == 400 and "章节插图" in response.json()["detail"]
    assert c.get(f"/api/projects/{pid}/jobs").json() == []
    assert c.post(f"/api/projects/{pid}/exports?simplified=true").status_code == 409
    assert c.get(f"/api/projects/{pid}/jobs").json() == []


def test_simplified_opt_in_is_scoped_to_reviewed_configuration(setup):
    c, pid, reader, raw = setup
    asset = add_illustration(setup)
    snapshot = report(c, pid)
    job = export(c, pid, snapshot)
    assert job["state"] == "completed", job
    assert job["result"]["webgal_compatibility"] == snapshot
    archive = reader.store.project_dir(pid) / "exports" / (job["id"] + ".zip")
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.read("storygal-source/original.txt") == raw
        manifest = json.loads(bundle.read("storygal-manifest.json"))
        assert manifest["webgal_compatibility"] == snapshot
        assert not any(asset["id"] in name for name in bundle.namelist())
    assert reader.load(pid)[1]["illustrations"][0]["image_asset_id"] == asset["id"]
    assert c.get(f"/api/projects/{pid}/source").content == raw


def test_change_after_review_requires_new_report_before_job_can_start(setup):
    c, pid, reader, _ = setup
    add_illustration(setup)
    snapshot = report(c, pid)
    revision, config = reader.load(pid)
    reader.save(pid, revision, {**config, "subtitle": "新增副标题"})
    response = c.post(
        f"/api/projects/{pid}/exports",
        params={"simplified": "true", "reader_revision": snapshot["reader_revision"]},
    )
    assert response.status_code == 409 and "重新查看" in response.json()["detail"]
    assert c.get(f"/api/projects/{pid}/jobs").json() == []
    assert {loss["field"] for loss in report(c, pid)["losses"]} == {"illustrations", "subtitle"}


def test_reader_change_during_packaging_prevents_publication(setup, monkeypatch):
    c, pid, reader, _ = setup
    add_illustration(setup)
    snapshot = report(c, pid)
    original = exporter.shutil.copy2
    changed = False

    def copy_and_change(source, destination, *args, **kwargs):
        nonlocal changed
        result = original(source, destination, *args, **kwargs)
        if not changed:
            changed = True
            revision, config = reader.load(pid)
            reader.save(pid, revision, {**config, "subtitle": "打包时更新"})
        return result

    monkeypatch.setattr(exporter.shutil, "copy2", copy_and_change)
    job = export(c, pid, snapshot)
    assert job["state"] == "failed" and "制作状态" in job["error"]
    assert list((reader.store.project_dir(pid) / "exports").iterdir()) == []


def test_reader_change_marks_new_webgal_export_stale_and_blocks_final_review(setup):
    c, pid, reader, _ = setup
    job = export(c, pid, report(c, pid))
    assert job["state"] == "completed", job
    review_url = f"/api/projects/{pid}/exports/{job['id']}/review"
    body = {"checks": {key: True for key in REVIEW_CHECKS}, "notes": "Test fixture"}
    assert c.post(review_url, json=body).status_code == 200
    revision, config = reader.load(pid)
    reader.save(pid, revision, {**config, "reading_layout": "illustrated"})
    assert c.get(f"/api/projects/{pid}/delivery").json()["stale"]
    assert c.post(review_url, json=body).status_code == 409
    assert c.get(job["result"]["play_url"]).status_code == 200


def test_historical_webgal_results_without_reader_revision_remain_reviewable(setup):
    c, pid, reader, _ = setup
    # Reproduce the historical result schema through the existing low-level exporter.
    jid = reader.store.start_job(pid)
    reader.store.finish_job(jid, result=exporter.export_project(reader.store, pid, jid))
    revision, config = reader.load(pid)
    reader.save(pid, revision, {**config, "subtitle": "Later reader-only change"})
    assert not c.get(f"/api/projects/{pid}/delivery").json()["stale"]
    response = c.post(
        f"/api/projects/{pid}/exports/{jid}/review",
        json={"checks": {key: True for key in REVIEW_CHECKS}, "notes": "Test fixture"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("illustrations", [{"id": "plate"}]),
        ("reading_layout", "illustrated"),
        ("cover_asset_id", "cover"),
        ("scenes", [{"id": "scene"}]),
        ("presentations", [{"id": "presentation"}]),
        ("map_profile", "chibi"),
        ("map_entries", [{"id": "entry"}]),
        ("title", "A custom chapter title"),
        ("subtitle", "A subtitle"),
    ],
)
def test_all_known_reader_only_features_are_reported_conservatively(field, value):
    config = {"title": "chapter", "reading_layout": "split", field: value}
    losses = webgal_losses(config, "chapter")
    assert len(losses) == 1 and losses[0]["field"] == field
    assert losses[0]["label"] and losses[0]["detail"]
