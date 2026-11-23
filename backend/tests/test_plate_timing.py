"""Reader reveal review is a private, edition-bound creator decision; not a quote classifier."""

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from test_plate_screening_workbench import CHECKS, apply, decision, get_review_job, state, timing
from test_reader_motion import project as project  # noqa: PLC0414 -- pytest fixture
from test_reader_motion import save

from storygal import plate_timing, reader_export
from storygal.reader import paragraphs

QUOTE = "雨点落进院里的水洼"
SECRET = "PRIVATE_REVEAL_REASON_49"
ROOT = Path(__file__).resolve().parents[2]


def placed(project):
    c, pid, _, _, config = project
    assert save(project, config).is_success
    prefix = "/api/projects/" + pid
    return c, prefix, state(c, prefix)


def test_valid_quote_is_not_a_semantic_verdict_and_only_signoff_is_gated(project):
    c, pid, reader, _, config = project
    config["illustrations"][0].update(title="最后的告别", description="最后一行才揭晓的告别。")
    c, prefix, initial = placed(project)
    plate = config["illustrations"][0]
    key = plate["id"]
    view = initial["display"][key]
    assert view["title"] == plate["title"] and view["alt"] == plate["description"]
    assert view["display_after_byte"] == plate["after_byte"]
    assert view["display_paragraph"] == view["paragraph"]
    assert initial["timing"]["plates"][key]["status"] == "unchecked"
    assert not initial["timing"]["ok"]
    # Motion worksheet accepts the exact quote, but does not speak for the reveal.
    screened = decision(c, prefix, initial, evidence=QUOTE).json()
    assert screened["report"]["ok"] and not screened["timing"]["ok"]
    before = reader.load(pid)
    job, sign = get_review_job(c, prefix)
    archive = c.get(job["result"]["download_url"]).content
    assert c.post(sign, json=CHECKS).status_code == 400
    revise = timing(
        c, prefix, screened, "revise", evidence=QUOTE, reason=SECRET + "：图题先说了告别。"
    )
    assert revise.is_success, revise.text
    held = revise.json()
    assert held["timing"]["counts"]["revise"] == 1 and not held["timing"]["ok"]
    assert held["report"] == screened["report"] and held["worksheet"] == screened["worksheet"]
    assert c.get(prefix + "/reader/content").is_success
    delivery = c.get(prefix + "/delivery").json()
    assert delivery["ready_for_export"] and not delivery["stale"]
    assert c.post(sign, json=CHECKS).status_code == 400
    assert reader.load(pid) == before
    assert c.get(prefix + "/bundle").is_success
    # Author revises public copy, not the source / placed visual or the citation.
    corrected = copy.deepcopy(config)
    corrected["illustrations"][0].update(title="雨中的石阶", description="深蓝色的静态底图。")
    assert save(project, corrected).is_success
    updated = state(c, prefix)
    assert updated["timing"]["plates"][key]["stale"]
    assert updated["timing"]["plates"][key]["status"] == "unchecked"
    assert SECRET not in str(updated)
    assert updated["report"] == screened["report"] and updated["worksheet"] == screened["worksheet"]
    assert timing(c, prefix, held, evidence=QUOTE).status_code == 409
    assert timing(c, prefix, updated, evidence="最后一行是还未发生的告别。").status_code == 400
    assert timing(c, prefix, updated, reason="  ").status_code == 400
    assert timing(c, prefix, updated, evidence="\ufeff ").status_code == 400
    assert timing(c, prefix, updated, binding="0" * 64).status_code == 409
    cleared = timing(c, prefix, updated, evidence=QUOTE, reason=SECRET + "：画面和说明都停在雨夜。")
    assert cleared.is_success, cleared.text
    assert cleared.json()["timing"]["ok"]
    assert c.post(sign, json=CHECKS).status_code == 409  # earlier content is immutable
    job2, sign2 = get_review_job(c, prefix)
    assert (
        c.post(sign2, json=CHECKS | {"timing_revision": held["timing"]["revision"]}).status_code
        == 409
    )
    signed = c.post(sign2, json=CHECKS)
    assert signed.is_success, signed.text
    assert c.get(prefix + "/delivery").json()["current_signoff"] == signed.json()
    assert c.get(job["result"]["download_url"]).content == archive
    reverted = timing(c, prefix, cleared.json(), "unchecked", evidence="", reason="").json()
    assert not reverted["timing"]["ok"] and not reverted["timing"]["plates"][key]["stale"]
    assert c.get(prefix + "/delivery").json()["current_signoff"] is None
    assert c.get(job2["result"]["play_url"]).is_success


@pytest.mark.parametrize(
    "field,value", [("title", "新图题"), ("description", ""), ("after_byte", 1)]
)
def test_only_changed_plate_rechecked_exact_return_never_revives_export_signoff(
    project, field, value
):
    c, pid, r, _, config = project
    second = dict(config["illustrations"][0], id="later", after_byte=r.blocks(pid)[-1]["byte_end"])
    config["illustrations"].append(second)
    c, prefix, old = placed(project)
    for plate in old["worksheet"]["plates"]:
        k = plate["plate_id"]
        old = decision(c, prefix, old, plate_id=k).json()
        old = timing(c, prefix, old, plate_id=k).json()
    _, url = get_review_job(c, prefix)
    assert c.post(url, json=CHECKS).is_success
    changed = copy.deepcopy(config)
    changed["illustrations"][0][field] = (
        r.blocks(pid)[1]["byte_end"] if field == "after_byte" else value
    )
    assert save(project, changed).is_success
    current = state(c, prefix)
    assert current["timing"]["counts"] == {"total": 2, "unchecked": 1, "revise": 0, "clear": 1}
    assert current["timing"]["plates"]["rain-court"]["stale"]
    assert current["timing"]["plates"]["later"] == old["timing"]["plates"]["later"]
    if field == "description":
        view = current["display"]["rain-court"]
        assert view["alt"] == view["title"] and view["description"] == ""
    # Content-addressed verdicts can match again, not the formal sign-off on the old revision.
    assert save(project, config).is_success
    assert state(c, prefix)["timing"] == old["timing"]
    assert c.get(prefix + "/delivery").json()["current_signoff"] is None
    assert c.post(url, json=CHECKS).status_code == 409


def test_reset_restore_import_privacy_and_obsolete_signoff(project):
    c, pid, reader, _, _ = project
    c, prefix, data = placed(project)
    data = decision(c, prefix, data).json()
    data = timing(c, prefix, data, reason=SECRET).json()
    sheet = data["worksheet"]
    assert "timing" not in json.dumps(sheet)
    assert apply(c, prefix, data, sheet).json()["timing"] == data["timing"]  # no-op v1 import
    job, url = get_review_job(c, prefix)
    record = c.post(url, json=CHECKS).json()
    assert record["plate_timing_revision"] == data["timing"]["revision"] and SECRET not in str(
        record
    )
    # Preserve a historical v1 sign-off; same motion rev must never bless its missing timing gate.
    del record["plate_timing_revision"]
    record.pop("plate_timing_binding")
    with reader.store.db() as db:
        db.execute(
            "UPDATE delivery_reviews SET data=? WHERE project_id=?", (json.dumps(record), pid)
        )
    delivery = c.get(prefix + "/delivery").json()
    assert delivery["records"] == [record] and delivery["current_signoff"] is None
    backup = c.get(prefix + "/bundle")
    actual = c.get(job["result"]["download_url"]).content
    for raw in (actual, backup.content):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                assert "private_plate_timings" not in name and SECRET.encode() not in z.read(name)
            # Not even the status/binding/revision project into JSON consumed by readers/restorers.
            public = z.read("reader.json" if raw is actual else "project.json")
            assert b"plate_timing" not in public and b"inventory_binding" not in public
            assert data["timing"]["plates"]["rain-court"]["binding"].encode() not in public
    assert SECRET not in c.get(prefix + "/reader/content").text
    restored = c.post("/api/project-bundles", files={"file": ("backup.zip", backup.content)})
    assert restored.status_code == 201, restored.text
    p2 = "/api/projects/" + restored.json()["id"]
    fresh = state(c, p2)
    assert not fresh["timing"]["ok"] and fresh["timing"]["revision"] == 0
    assert not fresh["timing"]["plates"]["rain-court"]["stale"]
    adopted = apply(c, p2, fresh, sheet, exact_copy=True)
    assert adopted.is_success and adopted.json()["report"]["ok"]
    assert adopted.json()["timing"] == fresh["timing"]
    _, restored_sign = get_review_job(c, p2)
    assert c.post(restored_sign, json=CHECKS).status_code == 400


def test_timing_writes_and_signoff_serialize_without_touching_motion(project, monkeypatch):
    c, prefix, new = placed(project)
    data = decision(c, prefix, new).json()
    data = timing(c, prefix, data).json()
    assert timing(c, prefix, new).status_code == 409
    _, url = get_review_job(c, prefix)
    record = c.post(url, json=CHECKS).json()
    assert record["archive_sha256"]
    desk = c.app.state.delivery.screening
    original = desk.state

    def raced(pid):
        inspected = original(pid)
        monkeypatch.setattr(desk, "state", original)
        assert timing(c, prefix, data, "revise").is_success
        return inspected

    monkeypatch.setattr(desk, "state", raced)
    assert c.post(url, json=CHECKS).status_code == 409
    delivery = c.get(prefix + "/delivery").json()
    assert delivery["records"] == [record] and not delivery["current_signoff"]
    assert not delivery["stale"] and delivery["ready_for_export"]
    assert state(c, prefix)["worksheet"] == data["worksheet"]


def test_empty_edition_needs_no_fictional_plate_or_attestation(project):
    c, pid, _, _, _ = project  # no placed image; candidate library is intentionally nonempty
    prefix = "/api/projects/" + pid
    data = state(c, prefix)["timing"]
    assert data["ok"] and data["counts"] == {"total": 0, "unchecked": 0, "clear": 0, "revise": 0}
    _, url = get_review_job(c, prefix)
    assert c.post(url, json=CHECKS).is_success


def test_old_immutable_runtime_requires_new_illustrated_export_before_signing(project):
    c, prefix, data = placed(project)
    data = decision(c, prefix, data).json()
    assert timing(c, prefix, data).is_success
    job, url = get_review_job(c, prefix)
    dist = reader_export.REPO / "frontend/dist/reader"
    checks = json.loads((dist / "runtime-checksums.json").read_bytes())
    (dist / "reader.js").write_bytes(b"/* another fully built renderer */")
    checks["reader.js"] = hashlib.sha256((dist / "reader.js").read_bytes()).hexdigest()
    (dist / "runtime-checksums.json").write_text(json.dumps(checks))
    res = c.post(url, json=CHECKS)
    assert res.status_code == 400 and "呈现版本" in res.json()["detail"]
    assert c.get(job["result"]["download_url"]).is_success
    _, new = get_review_job(c, prefix)
    assert c.post(new, json=CHECKS).is_success


def test_just_accepted_art_does_not_clear_replacement_or_tampered_source(project):
    c, pid, r, asset, config = project
    c, prefix, data = placed(project)
    data = timing(c, prefix, data).json()
    assert data["timing"]["ok"] and not data["report"]["ok"]  # independence in other direction
    same_bytes = r.path(pid, asset["id"]).read_bytes()
    new = r.upload(pid, r.load(pid)[0], same_bytes, "scene", "synthetic same pixels")
    r.accept(pid, r.load(pid)[0], new["id"], "accepted")
    config["illustrations"][0]["image_asset_id"] = new["id"]
    assert save(project, config).is_success
    now = state(c, prefix)
    assert now["timing"]["plates"]["rain-court"]["stale"]
    assert not now["timing"]["ok"] and not now["report"]["ok"]
    assert timing(c, prefix, data).status_code == 409
    path = r.store.project_dir(pid) / "source.utf8.txt"
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b"changed")
    assert c.get(prefix + "/plate-screening").status_code == 400
    assert timing(c, prefix, now).status_code == 400


def test_stale_tab_cannot_replace_a_concurrent_edit_inside_transaction(project, monkeypatch):
    c, prefix, data = placed(project)
    desk = c.app.state.delivery.screening
    original = desk.snapshot

    def raced(pid):
        inspected = original(pid)
        monkeypatch.setattr(desk, "snapshot", original)
        assert timing(c, prefix, data, "revise", reason=SECRET).is_success
        return inspected

    monkeypatch.setattr(desk, "snapshot", raced)
    assert timing(c, prefix, data, "clear").status_code == 409
    after = state(c, prefix)
    assert after["timing"]["plates"]["rain-court"]["reason"] == SECRET
    assert after["timing"]["revision"] == 1


def test_actual_edition_copy_and_delayed_reveal_not_guessed_from_id_or_byte_position():
    # Source boundaries and hashes from independent checked-in content fixtures. No images are
    # fabricated as real evidence. ScreeningDesk separately validates decoded original bytes.
    rebuild = json.loads((ROOT / "examples/chibi/rebuild-v0.2.0.json").read_bytes())
    images = json.loads((ROOT / "examples/chibi/visual-review-v0.2.0.json").read_bytes())["images"]
    raw = (ROOT / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt").read_bytes()
    canonical = hashlib.sha256(raw).hexdigest()
    blocks = paragraphs(raw)
    by_end = {b["byte_end"]: b for b in blocks}
    plates = [
        {**s, "id": "plan-" + s["id"], "description": s["moment"]} for s in rebuild["plan"]["shots"]
    ]
    media = {
        a["asset_id"]: {"id": a["asset_id"], "sha256": a["sha256"], "status": "accepted"}
        for a in images
    }
    book = {
        "project": {"canonical_sha256": canonical},
        "blocks": blocks,
        "config": {"illustrations": plates},
        "media": media,
    }
    current = {
        "work_id": "fixture",
        "source_sha256": canonical,
        "plates": [
            {
                "plate_id": p["id"],
                "after_byte": p["after_byte"],
                "image_asset_id": p["image_asset_id"],
                "image_sha256": media[p["image_asset_id"]]["sha256"],
                "width": 1672,
                "height": 941,
                "paragraph_start": by_end[p["after_byte"]]["byte_start"],
            }
            for p in plates
        ],
    }
    display, fresh = plate_timing.assess(book, current, None)
    assert len(display) == 12 and fresh["counts"]["unchecked"] == 12
    wind, fire = "plan-wind-in-tent", "plan-fire-panorama"
    assert (
        display[wind]["display_after_byte"] == 6136 and display[fire]["display_after_byte"] == 16035
    )
    assert display[wind]["display_paragraph"] == "不是孔明施妙計，周郎安得逞才能？"
    assert all(d["alt"] != d["description"] for d in display.values())
    assert "无人帐内近景" in display[wind]["alt"]
    fake_saved = (
        5,
        json.dumps(
            {k: {**v, "status": "clear", "reason": SECRET} for k, v in fresh["plates"].items()}
        ),
    )
    # A real edition-specific alt/caption projection changes (no edit to authored fields).
    wind_plate = next(p for p in plates if p["id"] == wind)
    media[wind_plate["image_asset_id"]]["status"] = "pending"
    now, stale = plate_timing.assess(book, current, fake_saved)
    assert now[wind]["alt"] == wind_plate["description"]
    assert now[wind]["display_after_byte"] == wind_plate["after_byte"]
    assert stale["plates"][wind]["stale"] and stale["plates"][fire]["status"] == "clear"
    # SHA of the entire canonical source is bound even to a still-unchanged earlier passage.
    changed = hashlib.sha256(raw + b" ").hexdigest()
    book["project"]["canonical_sha256"] = current["source_sha256"] = changed
    _, after_source = plate_timing.assess(book, current, fake_saved)
    assert after_source["counts"]["unchecked"] == 12 and SECRET not in str(after_source)
