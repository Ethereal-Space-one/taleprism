import json
import zipfile

import pytest
import test_reader_p6 as p6
from PIL import Image
from test_reader import export

from storygal.character_samples import ROOT, SAMPLES, import_candidate
from storygal.reader_casting import expanded_chibi


@pytest.fixture
def setup(tmp_path):
    base = p6.setup.__wrapped__(tmp_path)
    c, pid, r, raw = p6.ready(base)
    for key, name in [
        ("caocao", "曹操"),
        ("guanyu", "关羽"),
        ("lusu", "鲁肃"),
        ("huanggai", "黄盖"),
    ]:
        character = r.review.character(
            pid, r.review.state(pid)["revision"], name, [], "fixture", status="confirmed"
        )
        asset = import_candidate(
            r.review, pid, character["id"], r.review.state(pid)["revision"], key
        )
        r.review.accept_asset(pid, r.review.state(pid)["revision"], asset["id"], "accepted", True)
    zhou = next(a for a in r.review.state(pid)["characters"] if a["display_name"] == "周瑜")
    ill = import_candidate(r.review, pid, zhou["id"], r.review.state(pid)["revision"], "zhouyu_ill")
    return c, pid, r, raw, ill


def activate(setup):
    c, pid, r, raw, ill = setup
    r.review.accept_asset(pid, r.review.state(pid)["revision"], ill["id"], "accepted", False)
    revision, config = r.load(pid)
    r.save(pid, revision, expanded_chibi(r, pid, config))
    return c, pid, r, raw, ill


def test_portrait_budget_identity_and_source_scope(setup):
    c, pid, r, raw, ill = activate(setup)
    data = r.content(pid, strict=True)
    assert len(data["characters"]) == 6
    assert len([m for m in data["media"].values() if m["type"] == "figure"]) == 7
    assert all(len(p["cast"]) <= 2 for p in data["presentations"])
    used = {m["figure_asset_id"] for p in data["presentations"] for m in p["cast"]}
    assert len(used) == 7
    assert all(raw[: p["start_byte"]].decode() for p in data["presentations"] if p["start_byte"])
    assert c.get(f"/api/projects/{pid}/source").content == raw
    state = r.review.state(pid)
    zhou = next(c for c in state["characters"] if c["display_name"] == "周瑜")
    assert zhou["active_figure_id"] != ill["id"]
    assert len([a for a in state["assets"] if a["status"] == "accepted"]) == 7
    assert "".join(b["text"] for b in data["blocks"]) == "".join(
        "".join(x["text"] for x in b["runs"]) for b in data["blocks"]
    )


def test_states_follow_original_events_and_healthy_figures_are_not_used_after_injury(setup):
    _, pid, r, raw, ill = activate(setup)
    data = r.content(pid, strict=True)

    def at(quote):
        byte = raw.index(quote.encode())
        return next(p for p in reversed(data["presentations"]) if p["start_byte"] <= byte)

    def names(p):
        return {data["characters"][c["character_id"]]["name"] for c in p["cast"]}

    assert at("卻說周瑜立於山頂")["cast"] == []
    assert names(at("來見孔明，言周瑜猝病之事")) == {"鲁肃", "孔明"}
    assert ill["id"] in {c["figure_asset_id"] for c in at("瑜命請入")["cast"]}
    assert ill["id"] not in {c["figure_asset_id"] for c in at("瑜聞言大喜，矍然而起")["cast"]}
    assert names(at("黃蓋在第三隻火船上")) == {"黄盖"}
    assert at("黃蓋用刀一招")["cast"] == []
    assert at("正中肩窩，翻身落水")["cast"] == []
    assert names(at("操從其說，即縱馬向前")) == {"曹操", "关羽"}
    assert at("於是把馬頭勒回")["cast"] == []
    assert names(at("孔明忙離坐席")) == {"孔明", "关羽"}


def test_candidate_is_identity_scoped_and_state_stays_pending(setup):
    c, pid, r, _, ill = setup
    zhou = next(c for c in r.review.state(pid)["characters"] if c["display_name"] == "周瑜")
    endpoint = f"/api/projects/{pid}/characters/{zhou['id']}"
    choices = c.get(endpoint + "/codex-samples").json()
    assert {p["key"] for p in choices} == {"zhouyu", "zhouyu_ill"}
    assert ill["status"] == "pending" and ill["kind"] == "figure"
    assert (
        c.post(
            endpoint + "/codex-sample",
            json={"revision": r.review.state(pid)["revision"], "sample_key": "caocao"},
        ).status_code
        == 400
    )
    revision, config = r.load(pid)
    r.save(pid, revision, expanded_chibi(r, pid, config))
    assert r.content(pid)["preview"]
    with pytest.raises(ValueError, match="接受"):
        r.content(pid, strict=True)


def test_missing_identity_or_state_cannot_silently_reduce_coverage(setup):
    _, pid, r, _, ill = setup
    state = r.review.state(pid)
    r.review.accept_asset(pid, state["revision"], ill["id"], "rejected", False)
    with pytest.raises(ValueError, match="病中"):
        expanded_chibi(r, pid, r.load(pid)[1])


def test_export_keeps_all_used_portraits_and_prompt_provenance(setup):
    c, pid, r, raw, _ = activate(setup)
    job = export(c, pid)
    assert job["state"] == "completed", job
    with zipfile.ZipFile(r.store.project_dir(pid) / "exports" / (job["id"] + ".zip")) as z:
        content = json.loads(z.read("reader.json"))
        assert len([m for m in content["media"].values() if m["type"] == "figure"]) == 7
        assert z.read("storygal-source/original.txt") == raw
        assert "曹操" in z.read("storygal-source/characters/expansion-v1/prompts.json").decode()
        assert "storygal-source/characters/expansion-v1/PROVENANCE.md" in z.namelist()


def test_generated_pngs_have_real_transparency_and_manifest_matches_files():
    data = json.loads((ROOT / "expansion-v1/prompts.json").read_text())
    assert len(data["images"]) == 5
    for key in ["caocao", "guanyu", "lusu", "huanggai", "zhouyu_ill"]:
        with Image.open(ROOT / SAMPLES[key]["file"]) as im:
            assert im.mode == "RGBA" and im.size == (1024, 1536)
            assert im.getchannel("A").getextrema()[0] == 0
            assert im.getchannel("A").histogram()[0] > im.width * im.height // 5
