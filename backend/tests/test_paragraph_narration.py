"""Generated PCM only; exercise durable creator state, a real export and staged restore."""

import io
import json
import os
import struct
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from storygal import narration
from storygal.app import create_app
from storygal.reader import paragraphs
from storygal.text import sha256

TEXT = "\ufeff　　门还开着。\r\n  同一个楼梯。\r\n\t同一个楼梯。"
SECRET = "PRIVATE_TEST_CREDIT_DO_NOT_PUBLISH"


def riff(chunks):
    data = b"WAVE" + b"".join(
        k + struct.pack("<I", len(v)) + v + (b"\0" if len(v) % 2 else b"") for k, v in chunks
    )
    return b"RIFF" + struct.pack("<I", len(data)) + data


def wave(sample=33, channels=1, rate=24000, frames=3200, tags=False):
    fmt = struct.pack("<HHIIHH", 1, channels, rate, 2 * channels * rate, 2 * channels, 16)
    return riff(
        [(b"fmt ", fmt)]
        + ([(b"LIST", b"private-file-metadata")] if tags else [])
        + [(b"data", struct.pack("<h", sample) * channels * frames)]
    )


def create(client, studio=False):
    resp = client.post(
        "/api/projects",
        files={"file": ("original.txt", TEXT.encode())},
        data={"rights_status": "owned", "single_plate_studio": str(studio).lower()},
    )
    assert resp.status_code == 201, resp.text
    return "/api/projects/" + resp.json()["id"]


def upload(c, base, revision=0, start=None, body=None, credit=SECRET, public=False):
    if start is None:
        start = paragraphs(TEXT.encode())[1]["byte_start"]
    return c.post(
        base + "/reader/narrations",
        files={"file": ("private-personal-name.wav", body if body is not None else wave())},
        data={
            "revision": revision,
            "byte_start": start,
            "credit": credit,
            "publish_credit": str(public).lower(),
        },
    )


def decide(c, base, aid, revision, status):
    return c.patch(
        base + "/reader/narrations/" + aid, json={"revision": revision, "status": status}
    )


def read_zip(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return {n: z.read(n) for n in z.namelist()}


def export(c, base):
    req = c.post(base + "/reader/exports")
    assert req.status_code == 202, req.text
    return next(j for j in c.get(base + "/jobs").json() if j["id"] == req.json()["job_id"])


def packed(c, job):
    assert job["state"] == "completed", job
    files = read_zip(c.get(job["result"]["download_url"]).content)
    inventory = json.loads(files["storygal-delivery.json"])
    assert set(files) == set(inventory["files"]) | {"storygal-delivery.json"}
    assert all(sha256(files[k]) == v["sha256"] for k, v in inventory["files"].items())
    return files


@pytest.mark.parametrize("rate, channels", [(16000, 1), (24000, 1), (44100, 2), (48000, 2)])
def test_pcm_validation_preserves_frames_and_strips_riff_metadata(rate, channels):
    original = wave(rate=rate, channels=channels, tags=True)
    frames, duration = narration.canonical_wav(original)
    assert frames == wave(rate=rate, channels=channels) and b"private-file-metadata" not in frames
    assert duration == 3200 / rate


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"OggS",
        b"fake" * 150,
        wave()[:-1],
        wave() + b"private suffix",
        wave(channels=3),
        wave(rate=8000),
        wave(rate=96000),
        wave(sample=0),
        wave(frames=0),
        wave(frames=16000 * 120 + 1, rate=16000),
        riff([(b"fmt ", b"bad"), (b"data", b"abcd")]),
        riff([(b"fmt ", struct.pack("<HHIIHH", 3, 1, 24000, 48000, 2, 16)), (b"data", b"abcd")]),
        riff([(b"fmt ", struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16)), (b"data", b"odd")]),
        riff(
            [
                (b"fmt ", struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16)),
                (b"data", b"ab"),
                (b"data", b"cd"),
            ]
        ),
    ],
    ids=lambda x: sha256(x)[:7],
)
def test_malformed_wave_is_rejected(raw):
    with pytest.raises(ValueError):
        narration.canonical_wav(raw)


def test_real_export_does_not_publish_private_fields_audio_or_queue_from_candidates(tmp_path):
    c = TestClient(create_app(tmp_path))
    base = create(c)
    assert c.get(base + "/reader/narrations").json() == {"revision": 0, "takes": []}
    saved = upload(c, base, body=wave(tags=True))
    assert saved.status_code == 201, saved.text
    first = saved.json()["takes"][0]
    assert first["status"] == "pending" and not first["publish_credit"]
    assert c.get(first["url"]).content == wave()
    assert upload(c, base, revision=0).status_code == 409
    assert upload(c, base, revision=1, start=first["byte_start"] + 1).status_code == 400
    assert upload(c, base, revision=1, credit=" ").status_code == 400
    assert (
        len(list((c.app.state.store.project_dir(base.split("/")[-1]) / "narration").iterdir())) == 1
    )
    old = packed(c, export(c, base))
    assert not any(n.endswith(".wav") for n in old)
    assert json.loads(old["reader.json"])["schema_version"] == 2

    assert decide(c, base, first["id"], 1, "accepted").status_code == 200
    assert decide(c, base, first["id"], 1, "accepted").status_code == 409
    req = upload(c, base, revision=2, body=wave(94), credit="公开录音来源", public=True)
    assert req.status_code == 201
    second = next(t for t in req.json()["takes"] if t["status"] == "pending")
    new = packed(c, export(c, base))
    published = json.loads(new["reader.json"])
    assert published["schema_version"] == 4
    assert published["blocks"][1]["narration"] == {
        "id": first["id"],
        "duration": first["duration"],
        "label": "段落朗读",
    }
    assert [b["audio"] for b in published["blocks"]] == [[], [], []]
    assert not published["characters"] and len(published["media"]) == 1
    assert "narration" not in published["blocks"][2]  # repeated exact text, distinct paragraph
    assert published["media"][first["id"]].keys() == {
        "id",
        "sha256",
        "duration",
        "type",
        "origin",
        "url",
    }
    assert sum(n.endswith(".wav") for n in new) == 1
    assert new["media/" + first["id"] + ".wav"] == wave()
    assert all(
        SECRET.encode() not in data
        and second["id"].encode() not in data
        and b"private-file-metadata" not in data
        and b"private-personal-name" not in data
        for data in new.values()
    )
    assert [e["field"] for e in c.get(base + "/exports/compatibility").json()["losses"]] == [
        "narration"
    ]

    status = decide(c, base, second["id"], 3, "accepted")
    assert status.status_code == 200, status.text
    assert {t["id"]: t["status"] for t in status.json()["takes"]} == {
        first["id"]: "withdrawn",
        second["id"]: "accepted",
    }
    snap = packed(c, export(c, base))
    info = json.loads(snap["reader.json"])
    assert info["media"][second["id"]]["credit"] == "公开录音来源"
    assert snap["media/" + second["id"] + ".wav"] == wave(94) and first["id"] not in str(info)
    assert c.get(base + "/source").content == TEXT.encode()
    assert decide(c, base, first["id"], 4, "accepted").status_code == 400
    assert decide(c, base, second["id"], 4, "withdrawn").status_code == 200
    assert c.get(base + "/exports/compatibility").json()["compatible"]
    assert not c.get(base + "/reader/content").json()["media"]
    assert c.get(first["url"]).content == wave()  # withdrawn stays available only to maker
    assert new["media/" + first["id"] + ".wav"] == wave()  # prior publication is immutable


@pytest.mark.parametrize("studio", [False, True])
def test_v4_editable_roundtrip_keeps_history_and_optional_studio_entry(tmp_path, studio):
    c = TestClient(create_app(tmp_path / "old"))
    base = create(c, studio)
    if studio:
        old = c.get(base + "/bundle")
        assert json.loads(read_zip(old.content)["project.json"])["version"] == 3
    else:
        assert json.loads(read_zip(c.get(base + "/bundle").content)["project.json"])["version"] == 2
    first = upload(c, base).json()["takes"][0]
    assert decide(c, base, first["id"], 1, "accepted").status_code == 200
    second = upload(c, base, 2, body=wave(98)).json()["takes"][-1]
    third = upload(c, base, 3, body=wave(99)).json()["takes"][-1]
    assert decide(c, base, third["id"], 4, "withdrawn").status_code == 200
    archive = c.get(base + "/bundle")
    assert archive.status_code == 200, archive.text[:200]
    files = read_zip(archive.content)
    doc = json.loads(files["project.json"])
    assert doc["version"] == 4 and bool(doc["project"].get("single_plate_studio")) == studio
    assert len([n for n in files if n.startswith("narration/")]) == 3
    inbound = TestClient(create_app(tmp_path / "fresh"))
    restored = inbound.post("/api/project-bundles", files={"file": ("backup.zip", archive.content)})
    assert restored.status_code == 201 and not restored.json()["restore_issues"], restored.text
    new = "/api/projects/" + restored.json()["id"]
    assert new != base
    reopened = TestClient(create_app(tmp_path / "fresh"))
    state = reopened.get(new + "/reader/narrations").json()
    assert state["revision"] == 5
    assert {t["id"]: t["status"] for t in state["takes"]} == {
        first["id"]: "accepted",
        second["id"]: "pending",
        third["id"]: "withdrawn",
    }
    assert all(
        t["credit"] == SECRET
        and t["url"].startswith(new)
        and reopened.get(t["url"]).status_code == 200
        for t in state["takes"]
    )
    assert reopened.get(new + "/source").content == TEXT.encode()
    assert list(reopened.get(new + "/reader/content").json()["media"]) == [first["id"]]


def edit_backup(raw, mutation):
    f = read_zip(raw)
    doc = json.loads(f["project.json"])
    mutation(doc, f)
    f["project.json"] = json.dumps(doc).encode()
    m = json.loads(f.pop("manifest.json"))
    m["files"] = {n: sha256(v) for n, v in f.items()}
    f["manifest.json"] = json.dumps(m).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in f.items():
            z.writestr(k, v)
    return out.getvalue()


def test_restore_checks_source_audio_hashes_moved_identical_text_and_no_partial_import(tmp_path):
    c = TestClient(create_app(tmp_path / "a"))
    base = create(c)
    first = upload(c, base).json()["takes"][0]
    assert decide(c, base, first["id"], 1, "accepted").status_code == 200
    second = upload(c, base, 2, body=wave(9)).json()["takes"][-1]
    response = c.get(base + "/bundle")
    assert response.status_code == 200
    inbound = TestClient(create_app(tmp_path / "b"))
    duplicate = paragraphs(TEXT.encode())[2]

    def row(d):
        return next(t for t in d["records"][narration.TABLE] if t["id"] == first["id"])

    def rewrite_audio(d, f):
        raw = wave(123)
        f["narration/" + first["id"] + ".wav"] = raw
        row(d)["sha256"] = sha256(raw)

    def add_tags(d, f):
        raw = wave(tags=True)
        f["narration/" + first["id"] + ".wav"] = raw
        row(d)["sha256"] = sha256(raw)
        row(d)["binding_sha256"] = narration.binding(row(d))

    def two_active(d, f):
        next(t for t in d["records"][narration.TABLE] if t["id"] == second["id"])["status"] = (
            "accepted"
        )

    for mutate in [
        lambda d, f: row(d).update(
            byte_start=duplicate["byte_start"], byte_end=duplicate["byte_end"]
        ),
        lambda d, f: row(d).update(source_sha256="0" * 64),
        lambda d, f: row(d).update(original_sha256="0" * 64),
        lambda d, f: row(d).update(paragraph_sha256="0" * 64),
        lambda d, f: row(d).update(duration=9),
        lambda d, f: row(d).update(publish_credit="yes"),
        lambda d, f: row(d).update(status="active"),
        lambda d, f: d.update(version=2),
        rewrite_audio,
        add_tags,
        two_active,
        lambda d, f: f.pop("narration/" + second["id"] + ".wav"),
    ]:
        bad = inbound.post(
            "/api/project-bundles",
            files={"file": ("bad.zip", edit_backup(response.content, mutate))},
        )
        assert bad.status_code == 400, bad.text
        assert inbound.get("/api/projects").json() == []


def test_concurrent_candidates_and_acceptance_share_reader_revision(tmp_path):
    c = TestClient(create_app(tmp_path))
    base = create(c)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda n: upload(c, base, body=wave(n)), [15, 20]))
    assert sorted(r.status_code for r in results) == [201, 409]
    first = c.get(base + "/reader/narrations").json()["takes"][0]
    second = upload(c, base, 1, body=wave(25)).json()["takes"][-1]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda t: decide(c, base, t["id"], 2, "accepted"), [first, second]))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(c.get(base + "/reader/content").json()["media"]) == 1
    other = create(c)
    assert decide(c, other, first["id"], 0, "accepted").status_code == 404
    assert c.get(other + "/reader/narrations/" + first["id"] + "/file").status_code == 404


def test_corrupted_accepted_takes_fail_closed_but_withdrawal_remains_possible(tmp_path):
    c = TestClient(create_app(tmp_path))
    base = create(c)
    first = upload(c, base).json()["takes"][0]
    assert decide(c, base, first["id"], 1, "accepted").status_code == 200
    path = c.app.state.store.project_dir(base.split("/")[-1]) / "narration" / (first["id"] + ".wav")
    path.chmod(0o600)
    path.write_bytes(wave(10))
    content = c.get(base + "/reader/content").json()
    assert content["issues"] and not content["media"] and len(content["blocks"]) == 3
    assert export(c, base)["state"] == "failed" and c.get(base + "/bundle").status_code == 400
    assert decide(c, base, first["id"], 2, "withdrawn").status_code == 200
    assert export(c, base)["state"] == "completed"
    assert c.get(base + "/bundle").status_code == 400  # backups cannot drop unselected originals


@pytest.mark.parametrize("name", os.environ.get("TALEPRISM_TEST_OLD_EDITS", "").split(os.pathsep))
def test_existing_real_editable_editions_are_readable_without_invented_narration(tmp_path, name):
    if not name:
        pytest.skip("optional trusted historical editable ZIP(s); do not use private projects")
    raw = Path(name).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        old = json.loads(archive.read("project.json"))
        source = archive.read("original.txt")
    client = TestClient(create_app(tmp_path))
    added = client.post("/api/project-bundles", files={"file": ("historical.zip", raw)})
    assert added.status_code == 201, added.text
    pid = added.json()["id"]
    base = "/api/projects/" + pid
    assert client.get(base + "/source").content == source
    assert client.get(base + "/reader/narrations").json()["takes"] == []
    content = client.get(base + "/reader/content").json()
    assert content["schema_version"] in (2, 3)
    assert all("narration" not in b for b in content["blocks"])
    bundle = client.get(base + "/bundle")
    assert bundle.status_code == 200, bundle.text[:100]
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        reexport = json.loads(archive.read("project.json"))
        assert archive.read("original.txt") == source
        assert reexport["version"] == old["version"] and reexport["project"] == old["project"]
        assert not any(n.startswith("narration/") for n in archive.namelist())
        assert reexport["states"]["reader_states"] == old["states"]["reader_states"]
    # Prove actual older, fully illustrated editions can gain one new local cue too.
    revision = client.get(base + "/reader/narrations").json()["revision"]
    response = upload(
        client,
        base,
        revision,
        content["blocks"][0]["byte_start"],
        credit="generated migration check",
    )
    assert response.status_code == 201, response.text
    row = response.json()["takes"][0]
    assert decide(client, base, row["id"], revision + 1, "accepted").status_code == 200
    enriched = client.get(base + "/reader/content").json()
    assert enriched["schema_version"] == 4
    assert enriched["config"] == content["config"]
    assert enriched["blocks"][0]["narration"]["id"] == row["id"]
    assert len(enriched["media"]) == len(content["media"]) + 1


def test_changed_narration_during_export_never_leaks_stale_job(tmp_path, monkeypatch):
    from storygal import reader_export

    c = TestClient(create_app(tmp_path))
    base = create(c)
    take = upload(c, base).json()["takes"][0]
    assert decide(c, base, take["id"], 1, "accepted").status_code == 200
    real_copy = reader_export.copy_verified

    def withdraw_while_packing(source, target, digest):
        real_copy(source, target, digest)
        if target.name == take["id"] + ".wav":
            assert decide(c, base, take["id"], 2, "withdrawn").status_code == 200

    monkeypatch.setattr(reader_export, "copy_verified", withdraw_while_packing)
    job = export(c, base)
    assert job["state"] == "failed" and "状态" in job["error"]
    assert not list((c.app.state.store.project_dir(base.split("/")[-1]) / "exports").iterdir())
