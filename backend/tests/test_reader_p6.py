import copy
import json
import zipfile

import pytest
import test_reader as p5
from test_reader import export, sample_ready

from storygal.delivery import REVIEW_CHECKS
from storygal.reader_presentation import chibi


@pytest.fixture
def setup(tmp_path):
    return p5.setup.__wrapped__(tmp_path)


def ready(setup):
    c, pid, r, raw = sample_ready(setup)
    for name, key in [("孔明", "kongming"), ("周瑜", "zhouyu")]:
        state = c.get(f"/api/projects/{pid}/review").json()
        character = next(a for a in state["characters"] if a["display_name"] == name)
        response = c.patch(
            f"/api/projects/{pid}/characters/{character['id']}",
            json={
                "revision": state["revision"],
                "display_name": name,
                "aliases": character["aliases"],
                "status": "confirmed",
            },
        )
        assert response.status_code == 200
        state = c.get(f"/api/projects/{pid}/review").json()
        asset = c.post(
            f"/api/projects/{pid}/characters/{character['id']}/codex-sample",
            json={"revision": state["revision"], "sample_key": key},
        ).json()
        state = c.get(f"/api/projects/{pid}/review").json()
        assert (
            c.patch(
                f"/api/projects/{pid}/assets/{asset['id']}",
                json={"revision": state["revision"], "status": "accepted", "active": True},
            ).status_code
            == 200
        )
    rev, config = r.load(pid)
    r.save(pid, rev, chibi(r, pid, config))
    return c, pid, r, raw


def test_source_anchored_presentations_and_character_entrance(setup):
    _c, pid, r, raw = ready(setup)
    data = r.content(pid, strict=True)
    assert data["schema_version"] == 2
    presentations = data["presentations"]
    assert presentations[0]["cast"] == []
    entry = next(p for p in presentations if raw[p["start_byte"] :].startswith("瑜命請入".encode()))
    assert [data["characters"][m["character_id"]]["name"] for m in entry["cast"]] == ["孔明"]
    assert all(raw[p["start_byte"] :][:3].decode() for p in presentations)
    for b in data["blocks"]:
        assert "".join(run["text"] for run in b["runs"]) == b["text"]
        assert all(raw[a["byte_start"] : a["byte_end"]].decode() == a["text"] for a in b["runs"])
    assert {e["phase_id"] for e in data["map_entries"]} == {"opposition", "fire", "retreat"}


@pytest.mark.parametrize("invalid", ["byte", "slot", "scene", "event", "map"])
def test_invalid_presentation_contract(setup, invalid):
    _, pid, r, _ = ready(setup)
    rev, config = r.load(pid)
    config = copy.deepcopy(config)
    if invalid == "byte":
        config["presentations"][1]["start_byte"] += 1
    elif invalid == "slot":
        p = next(p for p in config["presentations"] if p["cast"])
        p["cast"].append(copy.deepcopy(p["cast"][0]))
    elif invalid == "scene":
        config["presentations"][0]["scene_id"] = "other"
    elif invalid == "event":
        config["presentations"][-1]["kind"] = "event"
    else:
        config["map_entries"][0]["place_ids"] = ["unknown"]
    with pytest.raises(ValueError):
        r.save(pid, rev, config)


def test_old_configuration_is_adapted_without_overwriting(setup):
    _, pid, r, _ = sample_ready(setup)
    with r.store.db() as db:
        before = db.execute("SELECT data FROM reader_states WHERE project_id=?", (pid,)).fetchone()[
            0
        ]
    assert r.content(pid)["presentations"]
    with r.store.db() as db:
        assert (
            db.execute("SELECT data FROM reader_states WHERE project_id=?", (pid,)).fetchone()[0]
            == before
        )


def test_notes_are_private_versioned_and_gate_final_review(setup):
    c, pid, r, raw = ready(setup)
    endpoint = f"/api/projects/{pid}/reader/editorial"
    issue = {
        "revision": 0,
        "anchor": r.blocks(pid)[1]["byte_start"],
        "category": "cast",
        "note": "PRIVATE_REVIEW_NOTE",
        "state": "open",
        "reason": "",
    }
    response = c.post(endpoint, json=issue)
    assert response.status_code == 200
    item = response.json()["issues"][0]
    assert c.post(endpoint, json=issue).status_code == 409
    assert b"PRIVATE_REVIEW_NOTE" not in c.get(f"/api/projects/{pid}/reader/content").content
    revision_before = r.load(pid)[0]
    job = export(c, pid)
    assert job["state"] == "completed", job
    with zipfile.ZipFile(r.store.project_dir(pid) / "exports" / (job["id"] + ".zip")) as z:
        data = json.loads(z.read("reader.json"))
        assert set(data) == {
            "schema_version",
            "project",
            "versions",
            "config",
            "blocks",
            "characters",
            "media",
            "map",
            "preview",
            "issues",
            "presentations",
            "map_entries",
        }
        assert all(b"PRIVATE_REVIEW_NOTE" not in z.read(name) for name in z.namelist())
        assert z.read("storygal-source/original.txt") == raw
    review_url = f"/api/projects/{pid}/exports/{job['id']}/review"
    body = {"checks": {k: True for k in REVIEW_CHECKS}, "notes": "automatic fixture only"}
    assert c.post(review_url, json=body).status_code == 400
    resolved = {k: item[k] for k in ["id", "anchor", "category", "note", "state", "reason"]}
    resolved.update(revision=1, state="deferred", reason="")
    assert c.post(endpoint, json=resolved).status_code == 400
    resolved["reason"] = "等待用户审查"
    assert c.post(endpoint, json=resolved).status_code == 200
    assert r.load(pid)[0] == revision_before
    assert c.post(review_url, json=body).status_code == 200
    rev, config = r.load(pid)
    r.save(pid, rev, {**config, "subtitle": "changed"})
    assert c.post(review_url, json=body).status_code == 409


def test_webgal_simplification_requires_explicit_choice(setup):
    c, pid, _, _ = ready(setup)
    response = c.post(f"/api/projects/{pid}/exports")
    assert response.status_code == 400 and "简化" in response.json()["detail"]


def test_editorial_change_during_final_review_is_serialized(setup, monkeypatch):
    c, pid, r, _ = ready(setup)
    job = export(c, pid)
    original = r.editorial.state
    changed = False

    def state_with_concurrent_edit(project_id):
        nonlocal changed
        snapshot = original(project_id)
        if not changed:
            changed = True
            r.editorial.save(
                project_id,
                snapshot["revision"],
                {
                    "anchor": r.blocks(pid)[1]["byte_start"],
                    "category": "visual",
                    "note": "concurrent note",
                    "state": "open",
                    "reason": "",
                },
            )
        return snapshot

    monkeypatch.setattr(r.editorial, "state", state_with_concurrent_edit)
    result = c.post(
        f"/api/projects/{pid}/exports/{job['id']}/review",
        json={"checks": {k: True for k in REVIEW_CHECKS}, "notes": "fixture only"},
    )
    assert result.status_code == 409
    assert c.get(job["result"]["play_url"]).status_code == 200
