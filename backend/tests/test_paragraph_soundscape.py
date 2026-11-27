"""Local author choices, separate audio kinds, publication allowlist and portable snapshots."""

import io
import json
import wave
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from test_paragraph_narration import edit_backup, export, packed, read_zip
from test_paragraph_narration import wave as voice_wav

from storygal import soundscape
from storygal.app import create_app
from storygal.text import sha256

RAW = "\ufeff　　雨🌧雨🌧在窗上。\r\n路边传来声音。\r\n路边传来声音。".encode()
END = "/reader/soundscapes"


def make(c):
    r = c.post(
        "/api/projects", files={"file": ("original.txt", RAW)}, data={"rights_status": "owned"}
    )
    assert r.is_success, r.text
    return "/api/projects/" + r.json()["id"]


@pytest.fixture
def book(tmp_path):
    c = TestClient(create_app(tmp_path / "local"))
    return c, make(c)


def post(c, b, rev=None, **kw):
    blocks = c.get(b + "/reader").json()["paragraphs"]
    payload = {
        "revision": c.get(b + END).json()["revision"] if rev is None else rev,
        "byte_start": blocks[1]["byte_start"],
        "evidence": "传来声音",
        "rain": True,
        "car_at": None,
    }
    return c.post(b + END, json=payload | kw)


def decide(c, b, aid, rev, status):
    return c.patch(b + END + "/" + aid, json={"revision": rev, "status": status})


def test_old_and_pending_only_books_do_not_change_reader_format(book):
    c, b = book
    assert c.get(b + END).json() == {"revision": 0, "takes": []}
    assert json.loads(read_zip(c.get(b + "/bundle").content)["project.json"])["version"] == 2
    r = post(c, b)
    assert r.status_code == 201, r.text
    t = r.json()["takes"][0]
    audio = c.get(t["url"])
    assert t["status"] == "pending" and t["duration"] == 12.0
    assert audio.status_code == 200 and len(audio.content) == 1_152_044
    assert audio.headers["cache-control"] == "no-store"
    with wave.open(io.BytesIO(audio.content)) as w:
        assert (w.getsampwidth(), w.getnchannels(), w.getframerate(), w.getnframes()) == (
            2,
            2,
            24000,
            288000,
        )
    data = packed(c, export(c, b))
    assert json.loads(data["reader.json"])["schema_version"] == 2
    assert all(t["id"].encode() not in raw for raw in data.values())
    assert not any(n.endswith(".wav") for n in data)
    assert c.get(b + "/exports/compatibility").json()["compatible"]


def test_exact_selection_with_non_bmp_and_duplicate_quote(book):
    c, b = book
    start = c.get(b + "/reader").json()["paragraphs"][0]["byte_start"]
    assert post(c, b, byte_start=start, evidence="雨🌧").status_code == 400
    exact = start + len("雨🌧".encode())
    for fields in [
        {"byte_start": start, "evidence": "雨🌧", "evidence_start": exact + 1},
        {"byte_start": start, "evidence": "路边"},
        {"byte_start": start + 1},
        {"evidence_start": len(RAW)},
        {"evidence": " "},
        {"evidence": "a" * 301},
        {"rain": False},
        {"car_at": 1},
        {"car_at": 11},
        {"car_at": 2.5},
        {"car_at": True},
        {"rain": 1},
        {"future_field": "no"},
    ]:
        assert post(c, b, **fields).status_code in (400, 422), fields
    assert c.get(b + END).json()["revision"] == 0
    r = post(c, b, byte_start=start, evidence="雨🌧", evidence_start=exact, car_at=7)
    assert r.status_code == 201, r.text
    t = r.json()["takes"][0]
    assert t["evidence_start"] == exact
    assert RAW[exact : exact + len(t["evidence"].encode())] == t["evidence"].encode()
    assert c.get(b + "/source").content == RAW


def test_published_mix_only_accepted_plus_independent_narration_and_legacy_webgal(
    book, tmp_path, monkeypatch
):
    c, b = book
    start = c.get(b + "/reader").json()["paragraphs"][1]["byte_start"]
    sr = post(c, b)
    first = sr.json()["takes"][0]
    fid = first["id"]
    assert decide(c, b, fid, 1, "accepted").status_code == 200
    sr = post(c, b, rev=2, rain=False, car_at=8)
    pending = next(t for t in sr.json()["takes"] if t["status"] == "pending")
    assert c.get(b + "/reader/content").json()["blocks"][1]["soundscape"]["description"] == "细雨"
    vr = c.post(
        b + "/reader/narrations",
        files={"file": ("my-private.wav", voice_wav())},
        data={
            "revision": 3,
            "byte_start": start,
            "credit": "UNPUBLISHED_VOICE_CREDIT",
            "publish_credit": "false",
        },
    )
    assert vr.is_success, vr.text
    voice = vr.json()["takes"][0]["id"]
    assert c.patch(
        b + "/reader/narrations/" + voice, json={"revision": 4, "status": "accepted"}
    ).is_success
    kept = packed(c, export(c, b))
    story = json.loads(kept["reader.json"])
    assert story["schema_version"] == 5
    block = story["blocks"][1]
    assert block["soundscape"] == {
        "id": fid,
        "duration": 12,
        "label": "段落声景",
        "description": "细雨",
    }
    assert block["audio"] == [] and block["narration"]["id"] == voice
    assert set(story["media"]) == {voice, fid}
    assert set(story["media"][fid]) == {"id", "sha256", "duration", "type", "origin", "url"}
    assert (
        story["media"][fid]["origin"] == "paragraph_soundscape"
        and story["media"][voice]["origin"] == "paragraph_narration"
    )
    assert kept["media/" + fid + ".wav"] == c.get(first["url"]).content
    assert not any("soundscape/" in n for n in kept)
    assert all(
        pending["id"].encode() not in v and b"UNPUBLISHED_VOICE_CREDIT" not in v
        for v in kept.values()
    )
    assert set(story) <= {
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
    assert b'"evidence_start"' not in kept["index.html"] and b'"car_at"' not in kept["reader.json"]
    assert (
        kept["storygal-source/original.txt"] == RAW
        and kept["storygal-source/source.utf8.txt"] == RAW
    )
    report = c.get(b + "/exports/compatibility").json()
    assert [v["field"] for v in report["losses"]] == ["narration", "soundscape"]
    assert c.post(b + "/exports").status_code == 400
    job = c.post(
        b + "/exports", params={"simplified": "true", "reader_revision": report["reader_revision"]}
    )
    done = next(j for j in c.get(b + "/jobs").json() if j["id"] == job.json()["job_id"])
    assert done["state"] == "completed", done
    web = read_zip(c.get(done["result"]["download_url"]).content)
    for n, v in web.items():
        assert not n.endswith(".wav") and all(
            w.encode() not in v for w in [fid, pending["id"], voice]
        )
    assert json.loads(web["storygal-manifest.json"])["checks"]["parser"]["passed"]
    # Actual issue history, both audio kinds and pending replacement survive together.
    issue = c.post(
        b + "/reader/editorial",
        json={
            "revision": 0,
            "category": "audio",
            "note": "PRIVATE_CUE_QA",
            "anchor": start,
            "state": "open",
            "reason": "",
        },
    )
    assert issue.is_success
    backup = c.get(b + "/bundle")
    assert backup.status_code == 200, backup.text[:200]
    files = read_zip(backup.content)
    doc = json.loads(files["project.json"])
    assert doc["version"] == 6 and len(doc["records"][soundscape.TABLE]) == 2
    assert len([n for n in files if n.endswith(".wav")]) == 3
    assert "PRIVATE_CUE_QA" in files["project.json"].decode()
    # Restoring cannot depend on a new render or a platform's libm sample results.
    from storygal import soundscape_audio

    monkeypatch.setattr(
        soundscape_audio,
        "render_soundscape",
        lambda *_: pytest.fail("restore/export must reuse saved PCM"),
    )
    receiver = TestClient(create_app(tmp_path / "receiver"))
    restored = receiver.post("/api/project-bundles", files={"file": ("author.zip", backup.content)})
    assert restored.is_success, restored.text
    nb = "/api/projects/" + restored.json()["id"]
    assert not restored.json()["restore_issues"] and not restored.json()["restore_notices"]
    assert receiver.get(nb + "/source").content == RAW
    assert receiver.get(nb + "/reader/editorial").json() == issue.json()
    state = receiver.get(nb + END).json()
    assert state["revision"] == 5
    assert [{k: v for k, v in t.items() if k != "url"} for t in state["takes"]] == [
        {k: v for k, v in t.items() if k != "url"} for t in c.get(b + END).json()["takes"]
    ]
    second = decide(receiver, nb, pending["id"], 5, "accepted")
    assert second.is_success and {t["status"] for t in second.json()["takes"]} == {
        "accepted",
        "withdrawn",
    }
    snapshot = packed(receiver, export(receiver, nb))
    new = json.loads(snapshot["reader.json"])
    assert (
        new["blocks"][1]["soundscape"]["description"] == "一辆车驶过"
        and new["blocks"][1]["narration"]["id"] == voice
    )
    assert fid not in new["media"] and pending["id"] in new["media"]
    assert all(b"PRIVATE_CUE_QA" not in v for v in snapshot.values())
    assert decide(receiver, nb, pending["id"], 6, "withdrawn").is_success
    quiet = packed(receiver, export(receiver, nb))
    final = json.loads(quiet["reader.json"])
    assert final["schema_version"] == 4 and list(final["media"]) == [voice]
    assert not any("soundscape" in block for block in final["blocks"])
    assert (
        kept["media/" + fid + ".wav"] == c.get(first["url"]).content
    )  # old publication remains immutable


def test_restored_bindings_fail_closed_and_no_partially_imported_work(book, tmp_path):
    c, b = book
    t = post(c, b, car_at=5).json()["takes"][0]
    assert decide(c, b, t["id"], 1, "accepted").is_success
    t2 = next(
        x for x in post(c, b, rain=False, car_at=2).json()["takes"] if x["status"] == "pending"
    )
    rr = c.get(b + "/bundle")
    assert rr.is_success
    target = TestClient(create_app(tmp_path / "reject"))

    def row(d):
        return next(r for r in d["records"][soundscape.TABLE] if r["id"] == t["id"])

    def broken_wav(d, f):
        path = "soundscape/" + t["id"] + ".wav"
        f[path] = voice_wav()
        row(d)["sha256"] = sha256(f[path])
        row(d)["binding_sha256"] = soundscape.binding(row(d))

    def moved(d, f):
        blocks = c.get(b + "/reader").json()["paragraphs"]
        different = blocks[2]
        row(d).update(byte_start=different["byte_start"], byte_end=different["byte_end"])

    def wrong_quote(d, f):
        row(d)["evidence_start"] += 1
        row(d)["binding_sha256"] = soundscape.binding(row(d))  # independently validate exact bytes

    def doubled(d, f):
        next(x for x in d["records"][soundscape.TABLE] if x["id"] == t2["id"])["status"] = (
            "accepted"
        )

    def invalid_palette(d, f):
        row(d).update(rain=False, car_at=None)
        row(d)["binding_sha256"] = soundscape.binding(row(d))

    for change in [
        broken_wav,
        moved,
        wrong_quote,
        doubled,
        invalid_palette,
        lambda d, f: row(d).update(car_at=6),
        lambda d, f: row(d).update(original_sha256="f" * 64),
        lambda d, f: row(d).update(unknown="field"),
        lambda d, f: d.update(version=5),
    ]:
        res = target.post(
            "/api/project-bundles", files={"file": ("invalid.zip", edit_backup(rr.content, change))}
        )
        assert res.status_code == 400, res.text
        assert target.get("/api/projects").json() == []


def test_revision_race_withdrawal_and_missing_asset(book, monkeypatch):
    c, b = book
    t = post(c, b).json()["takes"][0]
    other = make(c)
    assert c.get(other + END + "/" + t["id"] + "/file").status_code == 404
    assert decide(c, other, t["id"], 0, "accepted").status_code == 404
    t2 = next(
        x for x in post(c, b, rev=1, rain=True, car_at=10).json()["takes"] if x["id"] != t["id"]
    )
    assert decide(c, b, t["id"], 1, "accepted").status_code == 409
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda row: decide(c, b, row["id"], 2, "accepted"), [t, t2]))
    assert sorted(r.status_code for r in results) == [200, 409]
    state = c.get(b + END).json()
    winner = next(x for x in state["takes"] if x["status"] == "accepted")
    from storygal import reader_export

    real = reader_export.copy_verified

    def revoke_during_copy(src, dst, sha):
        real(src, dst, sha)
        if dst.name == winner["id"] + ".wav":
            assert decide(c, b, winner["id"], 3, "withdrawn").is_success

    monkeypatch.setattr(reader_export, "copy_verified", revoke_during_copy)
    job = export(c, b)
    assert job["state"] == "failed" and "状态" in job["error"]
    assert not list((c.app.state.store.project_dir(b.split("/")[-1]) / "exports").iterdir())
    still = next(x for x in state["takes"] if x["status"] == "pending")
    assert decide(c, b, still["id"], 4, "accepted").is_success
    path = c.app.state.reader.soundscapes.path(b.split("/")[-1], still["id"])
    path.chmod(0o600)
    path.write_bytes(b"broken")
    data = c.get(b + "/reader/content").json()
    assert data["issues"] and all("soundscape" not in block for block in data["blocks"])
    assert export(c, b)["state"] == "failed" and c.get(b + "/bundle").status_code == 400
    assert decide(c, b, still["id"], 5, "withdrawn").is_success
    assert export(c, b)["state"] == "completed"  # previous archived file not published
    assert c.get(b + "/bundle").status_code == 400  # a backup never drops an old damaged file


@pytest.mark.parametrize(("car_at", "description"), [(None, "风声"), (5, "风中一辆车驶过")])
def test_wind_has_own_source_bound_recipe_and_sanitized_label(book, tmp_path, car_at, description):
    c, b = book
    assert post(c, b, rain=True, wind=True).status_code == 400
    assert post(c, b, rain=False, wind="yes").status_code == 422
    first = post(c, b, rain=False, wind=True, car_at=car_at)
    assert first.is_success, first.text
    t = first.json()["takes"][0]
    assert t["wind"] and not t["rain"]
    assert decide(c, b, t["id"], 1, "accepted").is_success
    back = c.get(b + "/bundle")
    assert back.is_success
    a = TestClient(create_app(tmp_path / "wind-receiver"))
    r = a.post("/api/project-bundles", files={"file": ("wind.zip", back.content)})
    assert r.is_success, r.text
    n = "/api/projects/" + r.json()["id"]
    assert a.get(n + END).json()["takes"][0]["wind"] is True
    packed_book = packed(a, export(a, n))
    story = json.loads(packed_book["reader.json"])
    assert story["blocks"][1]["soundscape"]["description"] == description
    assert "不是现场录音、音乐或朗读" in packed_book["RIGHTS.txt"].decode()
    assert set(story["blocks"][1]["soundscape"]) == {"id", "duration", "label", "description"}
    assert "wind" not in story["media"][t["id"]]
    rain = post(c, b)
    rt = next(x for x in rain.json()["takes"] if x["status"] == "pending")
    assert rt["wind"] is False
    old = json.loads(read_zip(c.get(b + "/bundle").content)["project.json"])["records"][
        soundscape.TABLE
    ]
    assert "wind" not in next(x for x in old if x["id"] == rt["id"])
    # Older dry/rain recipe encodings retain their exact field set and digest.


def test_pencil_is_hand_staged_portable_and_not_a_weather_recipe(book, tmp_path, monkeypatch):
    c, b = book
    for flags in ({"rain": True}, {"wind": True}, {"car_at": 5}, {"pencil": 1}):
        assert post(c, b, **({"rain": False, "pencil": True} | flags)).status_code in (400, 422)
    assert c.get(b + END).json() == {"revision": 0, "takes": []}
    r = post(c, b, rain=False, pencil=True)
    assert r.status_code == 201, r.text
    take = r.json()["takes"][0]
    assert take["pencil"] is True and take["status"] == "pending"
    assert not any("soundscape" in blk for blk in c.get(b + "/reader/content").json()["blocks"])
    wav = c.get(take["url"]).content
    backup = c.get(b + "/bundle")
    assert backup.is_success
    archived = json.loads(read_zip(backup.content)["project.json"])
    row = archived["records"][soundscape.TABLE][0]
    assert archived["version"] == 6 and row["pencil"] is True and "wind" not in row
    assert row["binding_sha256"] == soundscape.binding(row)
    assert row["binding_sha256"] != soundscape.binding(row | {"pencil": False})

    # Rehash a malicious recipe as if legitimate; the format has to reject
    # impossible mixtures and wrong JSON types, not only stale hashes.
    receiver = TestClient(create_app(tmp_path / "pencil-receiver"))
    for bad in (
        {"rain": True},
        {"wind": True},
        {"car_at": 3},
        {"pencil": "paper"},
        {"pencil": False},
    ):

        def alter(doc, _files, flags=bad):
            copy = doc["records"][soundscape.TABLE][0]
            copy.update(flags)
            copy["binding_sha256"] = soundscape.binding(copy)

        tampered = edit_backup(backup.content, alter)
        res = receiver.post("/api/project-bundles", files={"file": ("bad.zip", tampered)})
        assert res.status_code == 400, res.text
    assert receiver.get("/api/projects").json() == []

    from storygal import soundscape_audio

    monkeypatch.setattr(
        soundscape_audio, "render_soundscape", lambda *a, **k: pytest.fail("no re-render")
    )
    restored = receiver.post(
        "/api/project-bundles", files={"file": ("editable.zip", backup.content)}
    )
    assert restored.is_success, restored.text
    base = "/api/projects/" + restored.json()["id"]
    recovered = receiver.get(base + END).json()["takes"][0]
    assert recovered["status"] == "pending" and recovered["pencil"] is True
    assert receiver.get(recovered["url"]).content == wav
    assert decide(receiver, base, take["id"], 1, "accepted").is_success
    exported = packed(receiver, export(receiver, base))
    reader = json.loads(exported["reader.json"])
    cue = reader["blocks"][1]["soundscape"]
    assert cue == {
        "id": take["id"],
        "duration": 12,
        "label": "段落声景",
        "description": "铅笔在纸上划过，随后静默",
    }
    assert reader["schema_version"] == 5 and exported["media/" + take["id"] + ".wav"] == wav
    assert (
        b'"pencil"' not in exported["reader.json"]
        and b'"evidence_start"' not in exported["reader.json"]
    )
    assert decide(receiver, base, take["id"], 2, "withdrawn").is_success
    assert not any(
        "soundscape" in v for v in receiver.get(base + "/reader/content").json()["blocks"]
    )


def test_reference_rain_matches_renderer_without_project_mutation(book):
    from storygal.soundscape_audio import render_soundscape

    client, project = book
    original = client.get(project + END).json()
    for _ in range(2):
        sample = client.get("/api/studio/preview/rain.wav")
        assert sample.status_code == 200 and sample.headers["content-type"] == "audio/wav"
        assert sample.content == render_soundscape(True, None)
    assert client.get(project + END).json() == original
