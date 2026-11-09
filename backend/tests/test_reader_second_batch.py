import json
import zipfile

import pytest
import test_reader_casting as first_batch
from PIL import Image
from test_reader import export
from test_reader_casting import activate


@pytest.fixture
def setup(tmp_path):
    return first_batch.setup.__wrapped__(tmp_path)

from storygal.character_samples import ROOT, SAMPLES, import_candidate
from storygal.reader_casting import expanded_chibi


@pytest.fixture
def eight(setup):
    c, pid, reader, raw, _ = activate(setup)
    for key, name in [("zhaoyun", "赵云"), ("zhangfei", "张飞")]:
        review = reader.review
        character = review.character(
            pid, review.state(pid)["revision"], name, [], "fixture", status="confirmed"
        )
        asset = import_candidate(review, pid, character["id"], review.state(pid)["revision"], key)
        review.accept_asset(pid, review.state(pid)["revision"], asset["id"], "accepted", True)
    result = c.post(
        f"/api/projects/{pid}/reader/choreography/second-sample",
        json={"revision": reader.load(pid)[0]},
    )
    assert result.status_code == 200, result.text
    return c, pid, reader, raw


def test_eight_roles_nine_figures_and_source_unchanged(eight):
    c, pid, reader, raw = eight
    data = reader.content(pid, strict=True)
    assert len(data["characters"]) == 8
    assert len([m for m in data["media"].values() if m["type"] == "figure"]) == 9
    assert len({m["figure_asset_id"] for p in data["presentations"] for m in p["cast"]}) == 9
    assert all(len(p["cast"]) <= 2 for p in data["presentations"])
    assert c.get(f"/api/projects/{pid}/source").content == raw


def test_arrivals_exits_and_actions_are_explicit(eight):
    _, pid, reader, raw = eight
    data = reader.content(pid, strict=True)

    def names(quote):
        at = raw.index(quote.encode())
        cue = next(p for p in reversed(data["presentations"]) if p["start_byte"] <= at)
        return {data["characters"][m["character_id"]]["name"] for m in cue["cast"]}

    assert names("須臾到，孔明、子龍登岸") == {"孔明", "赵云"}
    assert names("子龍可帶三千軍馬") == {"孔明", "赵云"}
    assert names("雲領計去了") == {"孔明"}
    assert names("又喚張飛曰") == {"孔明", "张飞"}
    assert names("飛領計去了") == {"孔明"}
    assert "赵云" not in names("趙雲拈弓搭箭")
    assert "张飞" not in names("為首乃燕人張翼德，橫矛立馬")


def test_second_recipe_is_explicit_and_old_recipe_remains_available(setup):
    c, pid, reader, _, _ = activate(setup)
    before = reader.load(pid)
    result = c.post(
        f"/api/projects/{pid}/reader/choreography/second-sample", json={"revision": before[0]}
    )
    assert result.status_code == 400 and "赵云" in result.json()["detail"]
    assert reader.load(pid) == before
    assert len(expanded_chibi(reader, pid, before[1])["presentations"]) == 40


def test_second_assets_transparency_and_export_provenance(eight):
    c, pid, reader, raw = eight
    manifest = json.loads((ROOT / "expansion-v2/prompts.json").read_text())
    assert len(manifest["images"]) == 2
    for key in ["zhaoyun", "zhangfei"]:
        with Image.open(ROOT / SAMPLES[key]["file"]) as image:
            assert image.mode == "RGBA" and image.size == (1024, 1536)
            assert image.getchannel("A").histogram()[0] > image.width * image.height // 5
    job = export(c, pid)
    assert job["state"] == "completed", job
    with zipfile.ZipFile(
        reader.store.project_dir(pid) / "exports" / (job["id"] + ".zip")
    ) as package:
        data = json.loads(package.read("reader.json"))
        assert len([m for m in data["media"].values() if m["type"] == "figure"]) == 9
        assert package.read("storygal-source/original.txt") == raw
        assert (
            "张飞" in package.read("storygal-source/characters/expansion-v2/prompts.json").decode()
        )
