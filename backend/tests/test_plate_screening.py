"""Editorial intent, exact media/text bindings, independent proof, and no input mutation."""

import io
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from storygal.plate_screening import assess, carriers_for_book, digest, make_worksheet, reconcile
from storygal.portable_reader import TEMPLATE, embed_story

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import screen_plates as cli
from reissue_autoplay import packed, summary


def png(color):
    out = io.BytesIO()
    Image.new("RGB", (37, 25), color).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def fake():
    lines = ["雨落在石上。", "窗纸不曾摆动。", "后来兵书中夹了一叶干花。"]
    src = "\n\n".join(lines).encode()
    images = {"art": png("#112233"), "cover": png("#112234"), "portrait": png("#112235")}
    media = {
        k: {
            "id": k,
            "url": f"./media/{k}.png",
            "sha256": digest(v),
            "width": 37,
            "height": 25,
            "type": "figure" if k == "portrait" else "image",
        }
        for k, v in images.items()
    }
    blocks = [
        {
            "text": s,
            "byte_start": src.index(s.encode()),
            "byte_end": src.index(s.encode()) + len(s.encode()),
        }
        for s in lines
    ]
    plate = {"id": "plate-A", "image_asset_id": "art", "after_byte": blocks[1]["byte_end"]}
    book = {
        "project": {"id": "private-work", "canonical_sha256": digest(src), "sha256": digest(src)},
        "config": {"illustrations": [plate], "title": "Rain", "cover_asset_id": "cover"},
        "media": media,
        "blocks": blocks,
        "preview": False,
    }
    return book, src, images


def sheet(fake):
    book, src, images = fake
    return make_worksheet(book, src, images.__getitem__)


def marked(blank, **updates):
    out = deepcopy(blank)
    out["plates"][0].update(
        {
            "decision": "still",
            "evidence": "雨落在石上",
            "observation": "原图只有闭窗与青石",
            "action": "停在石面",
            "protect": "不能让窗纸振动",
            "reason": "图中没有风",
        }
        | updates
    )
    return out


def archive(fake):
    book, src, images = fake
    files = {
        "reader.json": json.dumps(book).encode(),
        "index.html": embed_story(TEMPLATE, book).encode(),
        "storygal-source/source.utf8.txt": src,
        "storygal-source/original.txt": src,
        "assets/reader.js": b"an unknown reader script",
        "assets/reader.css": b".art{}",
    }
    files.update({f"media/{k}.png": v for k, v in images.items()})
    files["storygal-delivery.json"] = json.dumps({"files": summary(files)}).encode()
    return packed(files)


def rain(fake):
    book, src, _ = fake
    p = book["config"]["illustrations"][0]
    p["motion"] = {
        "version": 1,
        "effect": "rain-wet-ground",
        "width": 37,
        "height": 25,
        "source_sha256": digest(src),
        "image_sha256": book["media"]["art"]["sha256"],
        "after_byte": p["after_byte"],
        "reviewed": True,
        "playback_only": True,
        "areas": [[[0, 0], [1, 0], [1, 1]]],
        "ground": [],
        "drops": 7,
        "rings": 0,
    }
    return p["motion"]


def test_every_actual_placement_initially_unassessed(fake):
    book, src, images = fake
    # One piece of art at two different narrative anchors is two decisions; neither cover nor figure counts.
    book["config"]["illustrations"].append(
        {"id": "other", "image_asset_id": "art", "after_byte": len(src)}
    )
    current = sheet(fake)
    assert [p["plate_id"] for p in current["plates"]] == ["plate-A", "other"]
    assert all(
        p["image_sha256"] == digest(images["art"]) and p["width"] == 37 for p in current["plates"]
    )
    r = assess(current, current, src)
    assert not r["ok"] and r["counts"]["unassessed"] == 2 and r["counts"]["screened"] == 0


@pytest.mark.parametrize("choice", ["still", "deferred"])
def test_complete_judgments_never_animate(fake, choice):
    current = sheet(fake)
    r = assess(current, marked(current, decision=choice), fake[1])
    assert r["ok"] and r["counts"]["screened"] == 1 and r["counts"]["active"] == 0
    assert r["plates"][0]["evidence_bytes"] == [0, len("雨落在石上".encode())]


@pytest.mark.parametrize(
    "updates,tag",
    [
        ({"evidence": "后来兵书中"}, "UTF-8"),
        ({"evidence": "雨落在石面"}, "UTF-8"),
        ({"observation": "   "}, "observation"),
        ({"reason": ""}, "reason"),
        ({"protect": "\ufeff"}, "protect"),
        ({"action": ""}, "action"),
    ],
)
def test_missing_evidence_or_observation_cannot_pass(fake, updates, tag):
    current = sheet(fake)
    r = assess(current, marked(current, **updates), fake[1])
    assert not r["ok"] and any(tag in m for m in r["errors"])


@pytest.mark.parametrize("change", ["src", "id", "hash", "size", "ownership", "block", "duplicate"])
def test_inventory_rejects_stale_or_false_bindings(fake, change):
    book, _src, imgs = fake
    p, asset = book["config"]["illustrations"][0], book["media"]["art"]
    if change == "src":
        book["project"]["canonical_sha256"] = "0" * 64
    if change == "id":
        asset["id"] = "forged"
    if change == "hash":
        imgs["art"] = png("navy")
    if change == "size":
        asset["width"] = 99
    if change == "ownership":
        p["after_byte"] -= 1
    if change == "block":
        book["blocks"][0]["byte_start"] += 1
    if change == "duplicate":
        book["config"]["illustrations"].append(deepcopy(p))
    with pytest.raises(ValueError):
        sheet(fake)


def test_reconcile_preserves_same_binding_and_resets_each_change(fake):
    book, src, images = fake
    ini = sheet(fake)
    prior = marked(ini)
    assert reconcile(ini, prior) == (prior, [])
    changed = png("midnightblue")
    images["art"] = changed
    book["media"]["art"]["sha256"] = digest(changed)
    now = sheet(fake)
    with pytest.raises(ValueError, match="stale"):
        assess(now, prior, src)
    reset, notes = reconcile(now, prior)
    assert "plate-A" in notes[0] and reset["plates"][0]["decision"] == "unassessed"
    for key, value in (("paragraph_start", 0), ("after_byte", 9), ("image_asset_id", "different")):
        s = deepcopy(prior)
        s["plates"][0][key] = value
        assert reconcile(ini, s)[0] == ini
    with pytest.raises(ValueError, match="work_id"):
        reconcile(ini | {"work_id": "different-work"}, prior)
    assert reconcile(ini | {"source_sha256": "a" * 64}, prior)[0]["plates"] == ini["plates"]
    missing = ini | {"plates": []}
    assert "removed" in reconcile(missing, prior)[1][0]
    with pytest.raises(ValueError, match="incomplete"):
        assess(ini, missing, src)


def test_repeated_and_extra_claim_fields_cannot_smuggle_active(fake):
    current = sheet(fake)
    row = marked(current)["plates"][0]
    for bad in (
        current | {"plates": [row, row]},
        current | {"plates": [dict(row, active=True)]},
        current | {"schema_version": True},
        current | {"plates": [dict(row, width=True)]},
    ):
        with pytest.raises(ValueError):
            assess(current, bad, fake[1])


def test_unknown_and_unreviewed_and_null_stay_inert(fake):
    b, src, _ = fake
    m = rain(fake)
    current = sheet(fake)
    for new_value in (None, m | {"reviewed": False}, m | {"effect": "particles"}):
        b["config"]["illustrations"][0]["motion"] = new_value
        assert carriers_for_book(b, current, src) == {}


def test_an_assertion_or_recipe_is_not_a_receipt(fake):
    b, src, _ = fake
    rain(fake)
    current = sheet(fake)
    carriers = carriers_for_book(b, current, src)
    assert carriers == {"plate-A": "rain-wet-ground"}
    candidate = marked(
        current, decision="motion", verification="I saw live rain at 60fps and approved it"
    )
    r = assess(current, candidate, src, carriers=carriers)
    assert r["ok"] and r["plates"][0]["status"] == "candidate" and r["counts"]["active"] == 0
    for d in ("still", "deferred"):
        assert not assess(current, marked(current, decision=d), src, carriers=carriers)["ok"]
    with pytest.raises(ValueError, match="untrusted"):
        cli.receipt_evidence(
            json.dumps(
                {
                    "mode": "release",
                    "source_commit": cli.COMMIT_091,
                    "results": [{"changed_motion": ["plate-A"]}],
                }
            ).encode(),
            "a" * 64,
            current,
            carriers,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"after_byte": 2},
        {"width": 40},
        {"source_sha256": "a" * 64},
        {"image_sha256": "a" * 64},
        {"drops": 100000},
        {"areas": [[[0, 0], [1, 1], [1, 0], [0, 1]]]},
        {"playback_only": 1},
        {"note": "forged proof"},
        {"version": True},
    ],
)
def test_changed_or_malformed_render_data_cannot_support_motion(fake, change):
    m = rain(fake)
    m.update(change)
    with pytest.raises(ValueError):
        carriers_for_book(fake[0], sheet(fake), fake[1])


def test_observed_frames_require_positive_and_negative_authorized_binding(fake):
    current = sheet(fake)
    carriers = {"plate-A": "rain-wet-ground"}
    row = {
        "plate_id": "plate-A",
        "eligible_effect": "rain-wet-ground",
        "normal_frames": 2,
        "reduced_frames": 0,
    }

    def result(rows):
        return {"schema_version": 1, "browser_version": "157.1.0.0", "observations": rows}

    assert cli.observed_active(result([row]), current, carriers)[0] == {"plate-A"}
    for bad in (
        [row, row],
        [],
        [row | {"plate_id": "other"}],
        [row | {"eligible_effect": "particles"}],
        [row | {"normal_frames": True}],
        [row | {"normal_frames": 1}],
        [row | {"reduced_frames": 1}],
        [row | {"active": "yes"}],
    ):
        with pytest.raises(ValueError):
            cli.observed_active(result(bad), current, carriers)
    with pytest.raises(ValueError):
        cli.observed_active(result([row]), current, {})


def test_cli_nonmutating_study_and_bad_archive(fake, tmp_path):
    archive_file, blank, study, done = [
        tmp_path / n for n in ("reader.zip", "work.json", "study.json", "done.json")
    ]
    original = archive(fake)
    archive_file.write_bytes(original)
    assert cli.run(["init", str(archive_file), str(blank)]) == 0
    assert cli.run(["check", str(archive_file), str(blank)]) == 1
    binding = json.loads(blank.read_bytes())
    assert binding == sheet(fake)
    judgment = marked(binding)["plates"][0]
    row = {
        k: judgment[k]
        for k in ("plate_id", "decision", "evidence", "observation", "action", "protect", "reason")
    }
    fields = {"reader_sha256": digest(original), "plates": [row]}
    args = ["apply", str(archive_file), str(blank), "--study", str(study), "--out", str(done)]
    for bad in (
        fields | {"reader_sha256": "b" * 64},
        fields | {"plates": [row, row]},
        fields | {"plates": [row | {"active": True}]},
    ):
        study.write_text(json.dumps(bad))
        assert cli.run(args) == 2 and not done.exists()
    study.write_text(json.dumps(fields))
    assert cli.run(args) == 0 and cli.run(["check", str(archive_file), str(done)]) == 0
    assert (
        cli.run(["init", str(archive_file), str(archive_file)]) == 2
        and archive_file.read_bytes() == original
    )
    assert json.loads(blank.read_bytes()) == binding
    assert (
        cli.run(["check", str(archive_file), str(done), "--probe"]) == 2
    )  # never executes unknown JS
    _, files, b, _, _ = cli.inventory(archive_file)
    files["index.html"] += b"<script>1</script>"
    with pytest.raises(ValueError, match="HTML envelope"):
        cli.trust_probe_payload(files, b)
    for invalid in (b'{"plates":[],"plates":[]}', b'{"x":NaN}'):
        with pytest.raises(ValueError):
            cli.unique_json(invalid)


def test_candidate_needs_supported_effect_and_never_activates_on_its_own(fake):
    b, source, _ = fake
    ini = sheet(fake)

    def check(updates, carriers=None):
        return assess(ini, marked(ini, **updates), source, carriers=carriers)

    assert not check({"decision": "motion"})["ok"]
    prop = {
        "decision": "motion",
        "proposed_effect": "wave-impact-backwash",
        "verification": "active",
    }
    r = check(prop)
    assert r["ok"] and r["counts"]["screened"] == 1 and not r["counts"]["active"]
    assert r["plates"][0]["carrier"] is None and r["plates"][0]["status"] == "candidate"
    with pytest.raises(ValueError):
        check(prop | {"proposed_effect": "fire-embers"})
    assert not check(prop | {"decision": "still"})["ok"]
    assert not check(prop | {"decision": "deferred"})["ok"]
    rain(fake)
    bound = carriers_for_book(b, ini, source)
    assert not check(prop, bound)["ok"]
    assert check(prop | {"proposed_effect": "rain-wet-ground"}, bound)["ok"]


def test_sidecar_file_schema_matches_the_shared_model():
    published = json.loads((ROOT / "schemas/plate-motion-screening.json").read_bytes())
    assert published.pop("$schema").endswith("/2020-12/schema")
    assert published.pop("description")
    assert published == cli.Worksheet.model_json_schema()


def test_archive_content_and_canonical_bytes_must_be_one_lossless_source(fake, tmp_path):
    p = tmp_path / "copy.zip"
    p.write_bytes(archive(fake))
    _, files, book, canonical, _ = cli.inventory(p)

    def rewrite(original):
        files["storygal-source/original.txt"] = original
        book["project"]["sha256"] = digest(original)
        files["reader.json"] = json.dumps(book).encode()
        files["index.html"] = embed_story(TEMPLATE, book).encode()
        files["storygal-delivery.json"] = json.dumps({"files": summary(files)}).encode()
        p.write_bytes(packed(files))

    rewrite(canonical.decode().encode("gb18030"))
    assert cli.inventory(p)[3] == canonical
    rewrite(b"unrelated input")
    with pytest.raises(ValueError, match="same text"):
        cli.inventory(p)
