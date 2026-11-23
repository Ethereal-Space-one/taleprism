"""Actual local author flow, separate from motion recipes, playback and release."""

import copy
import io
import json
import zipfile

from test_reader_motion import motion, save, with_motion
from test_reader_motion import project as project  # noqa: PLC0414 -- pytest fixture
from test_reliability_integration import export

from storygal.delivery import REVIEW_CHECKS

MARK = "PRIVATE_SCREENING_SENTINEL"
CHECKS = {"checks": dict.fromkeys(REVIEW_CHECKS, True)}


def state(c, prefix):
    result = c.get(prefix + "/plate-screening")
    assert result.status_code == 200, result.text
    return result.json()


def decision(c, prefix, data, choice="still", **edits):
    r = data["worksheet"]["plates"][0]
    body = {
        "revision": data["revision"],
        "reader_revision": data["reader_revision"],
        "plate_id": r["plate_id"],
        "decision": choice,
        "observation": "合成的蓝底。",
        "action": "全幅不动。",
        "protect": "保护完整单色区域。",
        "reason": MARK,
        "evidence": "雨点落进院里的水洼",
        **edits,
    }
    return c.put(prefix + "/plate-screening/plate", json=body)


def timing(c, prefix, data, status="clear", plate_id=None, **edits):
    pid = plate_id or data["worksheet"]["plates"][0]["plate_id"]
    return c.put(
        prefix + "/plate-screening/timing",
        json={
            "revision": data["timing"]["revision"],
            "reader_revision": data["reader_revision"],
            "binding": data["timing"]["plates"][pid]["binding"],
            "plate_id": pid,
            "status": status,
            "evidence": data["display"][pid]["paragraph"],
            "reason": "合成回归夹具：已出现的场景，未透露后文。",
            **edits,
        },
    )


def apply(c, prefix, data, sheet, **opts):
    return c.post(
        prefix + "/plate-screening/import",
        json={
            "revision": data["revision"],
            "reader_revision": data["reader_revision"],
            "worksheet": json.dumps(sheet),
            **opts,
        },
    )


def get_review_job(c, prefix):
    job = export(c, prefix)
    assert job["state"] == "completed", job
    return job, prefix + f"/exports/{job['id']}/review"


def test_current_signoff_tracks_sheet_not_export_bytes_and_never_upgrades_legacy(project):
    c, pid, r, _, config = project
    assert save(project, config).is_success
    prefix = f"/api/projects/{pid}"
    d = state(c, prefix)
    assert not d["report"]["ok"] and d["report"]["counts"]["unassessed"] == 1
    job, url = get_review_job(c, prefix)  # draft reader stays available
    archive_url = job["result"]["download_url"]
    assert c.post(url, json=CHECKS).status_code == 400
    body = c.get(archive_url).content
    initial_config = r.load(pid)
    assert state(c, prefix)["worksheet"]["plates"][0]["decision"] == "unassessed"
    assert decision(c, prefix, d, evidence="最后一行是还未发生的告别。").status_code == 400
    saved = decision(c, prefix, d)
    assert saved.is_success, saved.text
    got = saved.json()
    assert got["report"]["ok"] and got["report"]["counts"]["active"] == 0
    assert r.load(pid) == initial_config
    assert decision(c, prefix, d).status_code == 409
    assert c.post(url, json=CHECKS | {"screening_revision": d["revision"]}).status_code == 409
    assert timing(c, prefix, got).is_success
    record = c.post(url, json=CHECKS).json()
    assert record["plate_screening_revision"] == got["revision"]
    assert c.get(prefix + "/delivery").json()["current_signoff"] == record
    # No-op exact import isn't an edit and does not invalidate this sign-off.
    assert apply(c, prefix, got, got["worksheet"]).json()["revision"] == got["revision"]
    assert c.get(prefix + "/delivery").json()["current_signoff"] == record
    updated = decision(
        c, prefix, got, "deferred", action="设想光向旁侧倾斜。", reason="此效果不支持，留待后续。"
    )
    assert updated.is_success, updated.text
    assert not updated.json()["report"]["counts"]["active"]
    assert r.load(pid) == initial_config
    delivery = c.get(prefix + "/delivery").json()
    assert delivery["ready_for_export"] and not delivery["stale"]
    assert delivery["records"] == [record] and delivery["current_signoff"] is None
    assert c.get(archive_url).content == body
    assert c.post(url, json=CHECKS).is_success
    now = c.get(prefix + "/delivery").json()["current_signoff"]
    assert now["plate_screening_revision"] == updated.json()["revision"]
    # Simulate historical import: older record predates the screening table.
    with r.store.db() as db:
        del now["plate_screening_revision"]
        db.execute("UPDATE delivery_reviews SET data=? WHERE project_id=?", (json.dumps(now), pid))
    delivery = c.get(prefix + "/delivery").json()
    assert delivery["records"] == [now] and delivery["current_signoff"] is None


def test_no_private_sheet_in_reader_or_backup_exact_restore_is_deliberate(project):
    c, pid, r, _, config = project
    assert save(project, config).is_success
    prefix = f"/api/projects/{pid}"
    d = state(c, prefix)
    assert decision(c, prefix, d, "motion").status_code == 400  # no supported treatment named
    chosen = decision(c, prefix, d, "motion", proposed_effect="wave-impact-backwash")
    assert chosen.is_success, chosen.text
    data = chosen.json()
    sheet = data["worksheet"]
    assert data["report"]["ok"] and data["report"]["counts"]["active"] == 0
    assert "motion" not in r.load(pid)[1]["illustrations"][0]
    assert MARK not in c.get(prefix + "/reader/content").text
    job, _ = get_review_job(c, prefix)
    reader_blob = c.get(job["result"]["download_url"]).content
    backup = c.get(prefix + "/bundle")
    assert backup.is_success
    for raw in [reader_blob, backup.content]:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert not any("screening" in n for n in z.namelist())
            assert not any(MARK.encode() in z.read(n) for n in z.namelist())
    restored = c.post("/api/project-bundles", files={"file": ("draft.zip", backup.content)})
    assert restored.status_code == 201, restored.text
    new_prefix = "/api/projects/" + restored.json()["id"]
    fresh = state(c, new_prefix)
    assert fresh["worksheet"]["work_id"] != sheet["work_id"] and not fresh["report"]["ok"]
    assert apply(c, new_prefix, fresh, sheet).status_code == 409
    wrong = copy.deepcopy(sheet)
    wrong["plates"][0]["image_sha256"] = "0" * 64
    assert apply(c, new_prefix, fresh, wrong, exact_copy=True).status_code == 400
    assert state(c, new_prefix)["revision"] == 0
    moved = apply(c, new_prefix, fresh, sheet, exact_copy=True)
    assert moved.is_success, moved.text
    assert (
        moved.json()["report"]["counts"]["motion"] == 1
        and moved.json()["worksheet"]["work_id"] == fresh["worksheet"]["work_id"]
    )


def test_stale_art_anchor_and_private_judgment_dont_operate_renderer(project):
    c, pid, r, asset, config = project
    assert save(project, with_motion(project, motion(project, reviewed=True))).is_success
    prefix = f"/api/projects/{pid}"
    d = state(c, prefix)
    marked = decision(c, prefix, d)
    assert marked.is_success, marked.text
    got = marked.json()
    assert not got["report"]["ok"] and "conflicts" in str(got["report"]["errors"])
    assert r.load(pid)[1]["illustrations"][0]["motion"]["reviewed"] is True
    _, url = get_review_job(c, prefix)
    assert c.post(url, json=CHECKS).status_code == 400
    changed = copy.deepcopy(config)
    changed["illustrations"][0]["after_byte"] = r.blocks(pid)[1]["byte_end"]
    assert save(project, changed).is_success
    new = state(c, prefix)
    assert (
        new["changed"] == ["rain-court"]
        and new["worksheet"]["plates"][0]["decision"] == "unassessed"
    )
    assert MARK not in str(new["worksheet"])
    assert apply(c, prefix, new, got["worksheet"]).status_code == 400
    assert decision(c, prefix, got).status_code == 409
    again = decision(c, prefix, new).json()
    assert again["report"]["ok"] and not again["changed"]
    image = r.upload(
        pid,
        r.load(pid)[0],
        r.path(pid, asset["id"]).read_bytes(),
        "scene",
        "synthetic identical pixels, new asset",
    )
    r.accept(pid, r.load(pid)[0], image["id"], "accepted")
    changed["illustrations"][0]["image_asset_id"] = image["id"]
    assert save(project, changed).is_success
    assert state(c, prefix)["changed"] == ["rain-court"]


def test_signoff_serializes_private_sheet_change(project, monkeypatch):
    c, pid, _, _, config = project
    assert save(project, config).is_success
    prefix = f"/api/projects/{pid}"
    d = decision(c, prefix, state(c, prefix)).json()
    assert timing(c, prefix, d).is_success
    _, url = get_review_job(c, prefix)
    desk = c.app.state.delivery.screening
    original = desk.state

    def raced(pid):
        snapshot = original(pid)
        monkeypatch.setattr(desk, "state", original)
        assert decision(c, prefix, d, "deferred").is_success
        return snapshot

    monkeypatch.setattr(desk, "state", raced)
    assert c.post(url, json=CHECKS).status_code == 409
    assert c.get(prefix + "/delivery").json()["records"] == []
