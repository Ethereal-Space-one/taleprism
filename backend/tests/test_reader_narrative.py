import copy
import json
import zipfile

import pytest
import test_reader_casting as first
import test_reader_second_batch as second
from test_reader import export

from storygal.reader_narrative import ROOT, catalog, import_candidates, narrative_chibi


@pytest.fixture
def draft(tmp_path):
    base = first.setup.__wrapped__(tmp_path)
    c, pid, reader, raw = second.eight.__wrapped__(base)
    import_candidates(reader, pid, reader.load(pid)[0])
    revision, config = reader.load(pid)
    reader.save(pid, revision, narrative_chibi(reader, pid, config))
    return c, pid, reader, raw


def accept(draft):
    c, pid, reader, raw = draft
    for asset in reader.state_assets(pid):
        if asset["status"] != "accepted":
            reader.accept(pid, reader.load(pid)[0], asset["id"], "accepted")
    return c, pid, reader, raw


def test_imported_art_stays_pending_and_does_not_change_source(draft):
    c, pid, reader, raw = draft
    candidates = [
        a for a in reader.state_assets(pid) if a.get("sample_key", "").startswith("narrative:")
    ]
    assert len(candidates) == 12 and all(a["status"] == "pending" for a in candidates)
    assert reader.content(pid)["preview"]
    with pytest.raises(ValueError, match="接受"):
        reader.content(pid, strict=True)
    assert c.get(f"/api/projects/{pid}/source").content == raw


def test_plates_follow_complete_source_paragraphs_and_preserve_full_text(draft):
    _, pid, reader, raw = accept(draft)
    data = reader.content(pid, strict=True)
    assert data["schema_version"] == 3
    assert data["config"]["reading_layout"] == "illustrated"
    plates = data["config"]["illustrations"]
    assert len(plates) == len({p["after_byte"] for p in plates}) == 12
    blocks = reader.blocks(pid)
    for spec in catalog():
        plate = next(p for p in plates if p["id"] == spec["key"])
        block = next(b for b in blocks if spec["marker"] in b["text"])
        assert plate["after_byte"] == block["byte_end"]
        assert (
            reader.path(pid, plate["image_asset_id"]).read_bytes()
            == (ROOT / spec["file"]).read_bytes()
        )
    assert all(len(p["cast"]) <= 2 for p in data["presentations"])
    painting_ids = {"painting-" + spec["key"] for spec in catalog()}
    assert all(not p["cast"] for p in data["presentations"] if p["id"] in painting_ids)
    assert "".join(b["text"] for b in data["blocks"]) == "".join(
        r["text"] for b in data["blocks"] for r in b["runs"]
    )
    assert raw == reader.review.source(pid)


def test_bad_foreign_duplicate_and_inside_paragraph_placements_are_rejected(draft):
    _, pid, reader, _ = draft
    for change in ["inside", "duplicate", "foreign"]:
        revision, original = reader.load(pid)
        config = copy.deepcopy(original)
        if change == "inside":
            config["illustrations"][0]["after_byte"] -= 1
        elif change == "duplicate":
            config["illustrations"][1]["after_byte"] = config["illustrations"][0]["after_byte"]
        else:
            config["illustrations"][0]["image_asset_id"] = "not-this-project"
        with pytest.raises(ValueError):
            reader.save(pid, revision, config)
        assert reader.load(pid) == (revision, original)


def test_reimport_keeps_acceptance_and_existing_files(draft):
    _, pid, reader, _ = accept(draft)
    before = reader.state_assets(pid)
    import_candidates(reader, pid, reader.load(pid)[0])
    assert reader.state_assets(pid) == before


def test_export_contains_all_paintings_and_their_sources(draft):
    c, pid, reader, raw = accept(draft)
    job = export(c, pid)
    assert job["state"] == "completed", job
    with zipfile.ZipFile(reader.store.project_dir(pid) / "exports" / (job["id"] + ".zip")) as z:
        data = json.loads(z.read("reader.json"))
        assert len(data["config"]["illustrations"]) == 12
        assert all(p["image_asset_id"] in data["media"] for p in data["config"]["illustrations"])
        assert z.read("storygal-source/original.txt") == raw
        assert "军帐" in z.read("storygal-source/narrative-v1/prompts.json").decode()
        assert "storygal-source/narrative-v1/PROVENANCE.md" in z.namelist()


def test_rejected_art_cannot_publish_even_if_used_only_in_plates(draft):
    _, pid, reader, _ = accept(draft)
    revision, config = reader.load(pid)
    aid = config["illustrations"][0]["image_asset_id"]
    config["presentations"] = [p for p in config["presentations"] if p["image_asset_id"] != aid]
    # Keep the full valid companion baseline while leaving this asset only in the plate list.
    from storygal.reader_casting import expanded_chibi

    config["presentations"] = expanded_chibi(reader, pid, config, second_batch=True)[
        "presentations"
    ]
    reader.save(pid, revision, config)
    reader.accept(pid, reader.load(pid)[0], aid, "rejected")
    with pytest.raises(ValueError, match="拒绝|接受"):
        reader.content(pid, strict=True)
