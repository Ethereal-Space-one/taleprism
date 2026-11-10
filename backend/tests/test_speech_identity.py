"""Speaker acceptance regressions using only temporary projects and synthetic WAVs."""

import io
import json
import wave
import zipfile

import pytest
from fastapi.testclient import TestClient

from storygal import llm, settings
from storygal import speech as module
from storygal.review import ConflictError, Review
from storygal.storage import Store
from storygal.text import sha256


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    # create_app also constructs a module-level app: isolate it before importing.
    monkeypatch.setenv("STORYGAL_DATA_DIR", str(tmp_path / "default"))
    monkeypatch.setattr(settings, "load_env", lambda _path: None)
    monkeypatch.setattr(llm, "api_key", lambda: "")
    caps = {
        "provider": "macos-say",
        "model": "synthetic-os-1",
        "version": 1,
        "format": "pcm_s16le/24000Hz/mono",
        "voices": ["one"],
        "available": True,
    }
    monkeypatch.setattr(module, "capabilities", lambda: caps.copy())
    monkeypatch.setattr(module, "voices", lambda: ["one"])
    monkeypatch.setattr(
        module.openai_speech,
        "capabilities",
        lambda: caps | {"provider": "openai-realtime", "available": False, "voices": []},
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("Real speech, subprocesses and cloud calls are forbidden in this test")

    monkeypatch.setattr(module.openai_speech, "render", forbidden)
    monkeypatch.setattr(module.subprocess, "run", forbidden)
    monkeypatch.setattr(llm, "analyze", forbidden)

    def render(_text, _voice, _speed, path):
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(24000)
            audio.writeframes(b"\x10\x10" * 2400)

    monkeypatch.setattr(module, "render", render)
    from storygal.app import create_app

    client = TestClient(create_app(tmp_path / "original"))
    raw = (
        "甲曰：「"
        + "这段原文需要按显示框分段。" * 10
        + "」甲曰：「再见。」乙曰：「世界。」丙曰：「等一等。」"
    ).encode()
    pid = client.app.state.store.create(raw, "identity.txt", "owned", "utf-8")["id"]
    review, speech = client.app.state.review, client.app.state.speech
    for character in review.state(pid)["characters"]:
        review.character(
            pid, review.state(pid)["revision"], character["display_name"], [], "", character["id"]
        )
        speech.profile(pid, speech.load(pid)[0], character["id"], "one", 180)
    for dialogue in review.state(pid)["dialogues"]:
        did = dialogue["id"]
        review.assign(pid, review.state(pid)["revision"], [did], dialogue["suggested_speaker_id"])
        speech.line(pid, speech.load(pid)[0], did, True, {}, "保留此条设置")
        speech.synthesize(pid, did)
        accept_candidate(speech, pid, did)
    assert len(speech.state(pid)["lines"][0]["segments"]) > 1
    return client, pid, raw


def accept_candidate(speech, pid, did):
    state = speech.state(pid)
    line = next(line for line in state["lines"] if line["id"] == did)
    speech.accept(
        pid, state["revision"], did, {s["key"]: s["candidate"]["id"] for s in line["segments"]}
    )


def portable_copy(client, pid, root, monkeypatch, *, cross_os=True, version=2):
    from storygal.app import create_app

    archive = client.get(f"/api/projects/{pid}/bundle")
    assert archive.status_code == 200
    raw = archive.content
    if version == 1:
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            files = {name: bundle.read(name) for name in bundle.namelist()}
        document = json.loads(files["project.json"])
        document["version"] = 1
        files["project.json"] = json.dumps(document, ensure_ascii=False).encode()
        manifest = json.loads(files["manifest.json"])
        manifest["files"]["project.json"] = sha256(files["project.json"])
        files["manifest.json"] = json.dumps(manifest).encode()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as bundle:
            for name, content in files.items():
                bundle.writestr(name, content)
        raw = output.getvalue()
    if cross_os:
        caps = module.capabilities()
        monkeypatch.setattr(
            module,
            "capabilities",
            lambda: caps | {"model": "synthetic-other-os", "available": False, "voices": []},
        )
        monkeypatch.setattr(module, "voices", list)
    restored = TestClient(create_app(root))
    result = restored.post("/api/project-bundles", files={"file": ("identity.zip", raw)})
    assert result.status_code == 201, result.text
    return restored, result.json()["id"]


@pytest.mark.parametrize("migration", ["native", "same-os", "cross-os"])
@pytest.mark.parametrize("action", ["single", "batch", "merge", "unknown"])
def test_same_profile_reassignment_requires_new_acceptance(
    recorded, tmp_path, monkeypatch, migration, action
):
    client, pid, raw = recorded
    if migration != "native":
        client, pid = portable_copy(
            client, pid, tmp_path / "restored", monkeypatch, cross_os=migration == "cross-os"
        )
    speech, review = client.app.state.speech, client.app.state.review
    before = speech.state(pid)
    before_config = speech.load(pid)[1]
    first, second, target, _other = before["lines"]
    assert first["profile"] == target["profile"]
    units, _ = review.presentation(pid)
    old_takes = speech.for_export(pid, units)[1]
    old_media = {take["id"]: speech.path(pid, take).read_bytes() for take in old_takes.values()}
    changed = {first["id"]}
    if action in {"batch", "merge"}:
        changed.add(second["id"])
    if action == "merge":
        response = client.post(
            f"/api/projects/{pid}/characters/{first['speaker_id']}/merge",
            json={"revision": review.state(pid)["revision"], "target_id": target["speaker_id"]},
        )
    else:
        # Include a duplicate and an unchanged speaker in the batch.
        ids = (
            [first["id"], second["id"], first["id"], target["id"]]
            if action == "batch"
            else [first["id"]]
        )
        response = client.patch(
            f"/api/projects/{pid}/dialogues",
            json={
                "revision": review.state(pid)["revision"],
                "dialogue_ids": ids,
                "speaker_id": None if action == "unknown" else target["speaker_id"],
            },
        )
    assert response.status_code == 200, response.text
    after = speech.state(pid)
    assert after["revision"] == before["revision"] + 1
    for old, current in zip(before["lines"], after["lines"], strict=True):
        if current["id"] in changed:
            assert all(segment["accepted"] is None for segment in current["segments"])
        else:
            assert current["segments"] == old["segments"]
    expected = json.loads(json.dumps(before_config))
    for did in changed:
        expected["lines"][did].pop("accepted")
    assert speech.load(pid)[1] == expected
    with pytest.raises(ValueError, match="未接受|过期|归属"):
        speech.for_export(pid, review.presentation(pid)[0])
    assert review.source(pid) == raw
    for take in old_takes.values():
        assert speech.path(pid, take).read_bytes() == old_media[take["id"]]
        assert (
            client.get(f"/api/projects/{pid}/speech/takes/{take['id']}").content
            == old_media[take["id"]]
        )

    if action != "merge":
        # Changing back must not revive any old approval, including native cached takes.
        review.assign(pid, review.state(pid)["revision"], list(changed), first["speaker_id"])
        assert speech.load(pid)[1] == expected
        with pytest.raises(ValueError, match="未接受|过期"):
            speech.for_export(pid, review.presentation(pid)[0])
        if migration != "cross-os":
            for did in changed:
                accept_candidate(speech, pid, did)
            assert len(speech.for_export(pid, review.presentation(pid)[0])[1]) == len(old_takes)

    # Revocation survives closing/reopening and another portable export/import.
    if action == "merge" or migration == "cross-os":
        restored, new_pid = portable_copy(client, pid, tmp_path / "again", monkeypatch)
        for line in restored.app.state.speech.state(new_pid)["lines"]:
            assert all(bool(s["accepted"]) == (line["id"] not in changed) for s in line["segments"])


@pytest.mark.parametrize("version", [1, 2])
def test_unchanged_audio_roundtrips_across_os_and_legacy_bundles(
    recorded, tmp_path, monkeypatch, version
):
    client, pid, raw = recorded
    original_caps = module.capabilities()
    original = client.app.state.speech.state(pid)
    expected = {
        segment["accepted"]["id"]: segment["accepted"]["sha256"]
        for line in original["lines"]
        for segment in line["segments"]
    }
    client, pid = portable_copy(client, pid, tmp_path / "other-os", monkeypatch, version=version)
    for iteration in range(2):
        assert client.get(f"/api/projects/{pid}/source").content == raw
        content = client.get(f"/api/projects/{pid}/reader/content")
        assert content.status_code == 200, content.text
        sounds = [a for a in content.json()["media"].values() if a["type"] == "audio"]
        assert len(sounds) == len(expected)
        for sound in sounds:
            audio = client.get(sound["url"])
            assert audio.status_code == 200
            assert sha256(audio.content) in expected.values()
        response = client.post(f"/api/projects/{pid}/reader/exports")
        assert response.status_code == 202, response.text
        job = client.get(f"/api/projects/{pid}/jobs").json()[0]
        assert job["state"] == "completed", job.get("error")
        if iteration == 0:
            # Return to the original OS; do not generate or replace the original WAVs.
            monkeypatch.setattr(module, "capabilities", lambda: original_caps)
            client, pid = portable_copy(client, pid, tmp_path / "back", monkeypatch, cross_os=False)
    assert {
        s["accepted"]["id"]: s["accepted"]["sha256"]
        for line in client.app.state.speech.state(pid)["lines"]
        for s in line["segments"]
    } == expected


def test_unrelated_edits_and_same_speaker_preserve_acceptance(recorded):
    client, pid, _raw = recorded
    speech, review = client.app.state.speech, client.app.state.review
    before = speech.state(pid)
    config = speech.load(pid)
    first = before["lines"][0]
    review.assign(pid, review.state(pid)["revision"], [first["id"]], first["speaker_id"])
    review.character(
        pid, review.state(pid)["revision"], "甲的新称呼", ["甲"], "身份补充", first["speaker_id"]
    )
    assert speech.load(pid) == config
    assert [l["segments"] for l in speech.state(pid)["lines"]] == [
        l["segments"] for l in before["lines"]
    ]


def test_merge_of_suggestion_only_preserves_acceptance(recorded):
    client, pid, _raw = recorded
    speech, review = client.app.state.speech, client.app.state.review
    first, second, target, other = speech.state(pid)["lines"]
    for line in [first, second]:
        review.assign(pid, review.state(pid)["revision"], [line["id"]], target["speaker_id"])
        speech.synthesize(pid, line["id"])
        accept_candidate(speech, pid, line["id"])
    before = speech.load(pid)
    review.merge(pid, review.state(pid)["revision"], first["speaker_id"], other["speaker_id"])
    assert speech.load(pid) == before
    assert review.state(pid)["dialogues"][0]["suggested_speaker_id"] == other["speaker_id"]
    assert speech.for_export(pid, review.presentation(pid)[0])[1]


@pytest.mark.parametrize("action", ["assign", "merge"])
def test_failed_speaker_transaction_rolls_back_acceptance(recorded, monkeypatch, action):
    client, pid, _raw = recorded
    speech, review = client.app.state.speech, client.app.state.review
    before_review, before_speech = review.state(pid), speech.load(pid)
    first, _second, target, _other = speech.state(pid)["lines"]
    invalidate = review.invalidate_speech_acceptance

    def fail_after_invalidation(db, project_id, ids):
        invalidate(db, project_id, ids)
        raise RuntimeError("injected failure before commit")

    monkeypatch.setattr(review, "invalidate_speech_acceptance", fail_after_invalidation)
    with pytest.raises(RuntimeError, match="injected"):
        if action == "merge":
            review.merge(pid, before_review["revision"], first["speaker_id"], target["speaker_id"])
        else:
            review.assign(pid, before_review["revision"], [first["id"]], target["speaker_id"])
    assert review.state(pid) == before_review
    assert speech.load(pid) == before_speech
    assert speech.for_export(pid, review.presentation(pid)[0])[1]


@pytest.mark.parametrize("previously_accepted", [True, False])
def test_in_flight_accept_cannot_restore_old_speaker_approval(
    recorded, monkeypatch, previously_accepted
):
    client, pid, _raw = recorded
    speech, review = client.app.state.speech, client.app.state.review
    first, _second, target, _other = speech.state(pid)["lines"]
    if not previously_accepted:
        speech.mutate(
            pid,
            speech.load(pid)[0],
            "test.unaccept",
            lambda data: data["lines"][first["id"]].pop("accepted"),
        )
    mutate = speech.mutate

    def assign_before_accept_commit(project_id, revision, action, fn):
        assert action == "speech.accept"
        review.assign(pid, review.state(pid)["revision"], [first["id"]], target["speaker_id"])
        mutate(project_id, revision, action, fn)

    monkeypatch.setattr(speech, "mutate", assign_before_accept_commit)
    with pytest.raises(ConflictError):
        accept_candidate(speech, pid, first["id"])
    assert not speech.load(pid)[1]["lines"][first["id"]].get("accepted")


def test_concurrent_reassignment_cannot_mix_old_acceptance_with_new_review(recorded, monkeypatch):
    client, pid, _raw = recorded
    speech, review = client.app.state.speech, client.app.state.review
    first, _second, target, _other = speech.state(pid)["lines"]
    presentation = review.presentation

    def assign_before_presentation(project_id):
        review.assign(pid, review.state(pid)["revision"], [first["id"]], target["speaker_id"])
        return presentation(project_id)

    monkeypatch.setattr(review, "presentation", assign_before_presentation)
    with pytest.raises(ConflictError):
        speech.state(pid)


def test_changed_speaker_must_explicitly_accept_matching_take(recorded):
    client, pid, _raw = recorded
    speech, review = client.app.state.speech, client.app.state.review
    first, _second, target, _other = speech.state(pid)["lines"]
    old_ids = {s["key"]: s["accepted"]["id"] for s in first["segments"]}
    review.assign(pid, review.state(pid)["revision"], [first["id"]], target["speaker_id"])
    with pytest.raises(ValueError, match="不匹配"):
        speech.accept(pid, speech.load(pid)[0], first["id"], old_ids)
    speech.synthesize(pid, first["id"])
    with pytest.raises(ValueError, match="未接受|过期"):
        speech.for_export(pid, review.presentation(pid)[0])
    accept_candidate(speech, pid, first["id"])
    assert speech.for_export(pid, review.presentation(pid)[0])[1]
    review.assign(pid, review.state(pid)["revision"], [first["id"]], first["speaker_id"])
    with pytest.raises(ValueError, match="未接受|过期"):
        speech.for_export(pid, review.presentation(pid)[0])


def test_review_without_speech_state_remains_usable(tmp_path):
    store = Store(tmp_path)
    review = Review(store)
    pid = store.create("甲曰：「你好。」".encode(), "review.txt", "owned", "utf-8")["id"]
    initial = review.state(pid)
    character, dialogue = initial["characters"][0], initial["dialogues"][0]
    review.character(pid, initial["revision"], "甲", [], "", character["id"])
    review.assign(pid, review.state(pid)["revision"], [dialogue["id"]], character["id"])
    assert review.state(pid)["dialogues"][0]["speaker_id"] == character["id"]
    speech = module.Speech(store, review)
    # Existing speech table, but still no per-project state.
    review.assign(pid, review.state(pid)["revision"], [dialogue["id"]], None)
    assert speech.load(pid) == (0, {"profiles": {}, "lines": {}})
    review.assign(pid, review.state(pid)["revision"], [dialogue["id"]], character["id"])
    assert speech.load(pid) == (1, {"profiles": {}, "lines": {}})
