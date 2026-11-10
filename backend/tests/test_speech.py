import wave

import pytest
from fastapi.testclient import TestClient

from storygal import speech as module
from storygal.app import create_app


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(
        module,
        "capabilities",
        lambda: {
            "provider": "macos-say",
            "model": "1",
            "version": 1,
            "format": "pcm",
            "voices": ["one", "two"],
            "available": True,
        },
    )
    monkeypatch.setattr(module, "voices", lambda: ["one", "two"])
    calls = []

    def render(text, voice, speed, path):
        calls.append((text, voice, speed))
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(24000)
            out.writeframes(b"\x10\x10" * 2400)

    monkeypatch.setattr(module, "render", render)
    c = TestClient(create_app(tmp_path))
    pid = c.post(
        "/api/projects",
        files={"file": ("x.txt", "甲曰：「你好。」乙曰：「世界。」".encode())},
        data={"rights_status": "owned"},
    ).json()["id"]
    review = c.app.state.review
    state = review.state(pid)
    for char in state["characters"]:
        review.character(
            pid, review.state(pid)["revision"], char["display_name"], [], "", char["id"]
        )
    for d in review.state(pid)["dialogues"]:
        review.assign(pid, review.state(pid)["revision"], [d["id"]], d["suggested_speaker_id"])
    s = c.app.state.speech
    for line in s.state(pid)["lines"]:
        s.profile(pid, s.state(pid)["revision"], line["speaker_id"], "one", 180)
        s.line(pid, s.state(pid)["revision"], line["id"], True, {})
    return c, pid, s, calls


def test_cache_correction_force_accept_and_export(setup):
    c, pid, s, calls = setup
    lines = s.state(pid)["lines"]
    for line in lines:
        assert s.synthesize(pid, line["id"])["generated"] == 1
    assert s.synthesize(pid, lines[0]["id"])["reused"] == 1
    assert len(calls) == 2
    for line in s.state(pid)["lines"]:
        s.accept(
            pid,
            s.state(pid)["revision"],
            line["id"],
            {x["key"]: x["candidate"]["id"] for x in line["segments"]},
        )
    units, _ = c.app.state.review.presentation(pid)
    assert len(s.for_export(pid, units)[1]) == 2
    old = s.state(pid)["lines"][1]["segments"][0]["accepted"]["id"]
    line = s.state(pid)["lines"][0]
    s.line(pid, s.state(pid)["revision"], line["id"], True, {line["segments"][0]["key"]: "您好。"})
    with pytest.raises(ValueError, match="过期"):
        s.for_export(pid, units)
    s.synthesize(pid, line["id"])
    assert len(calls) == 3
    assert s.state(pid)["lines"][1]["segments"][0]["accepted"]["id"] == old
    line = s.state(pid)["lines"][0]
    first = line["segments"][0]["candidate"]["id"]
    s.synthesize(pid, line["id"], force=True)
    assert s.state(pid)["lines"][0]["segments"][0]["candidate"]["id"] != first
    assert len(calls) == 4


def test_profile_changes_invalidate_only_role_and_corrupt_audio_blocked(setup):
    _c, pid, s, _ = setup
    for line in s.state(pid)["lines"]:
        s.synthesize(pid, line["id"])
        updated = next(l for l in s.state(pid)["lines"] if l["id"] == line["id"])
        s.accept(
            pid,
            s.state(pid)["revision"],
            line["id"],
            {x["key"]: x["candidate"]["id"] for x in updated["segments"]},
        )
    first, second = s.state(pid)["lines"]
    s.profile(pid, s.state(pid)["revision"], first["speaker_id"], "two", 190)
    assert not s.state(pid)["lines"][0]["segments"][0]["accepted"]
    assert s.state(pid)["lines"][1]["segments"][0]["accepted"]
    take = second["segments"][0]["accepted"]
    path = s.path(pid, take)
    path.chmod(0o644)
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="哈希"):
        s.path(pid, take)


def test_unknown_speaker_and_stale_revision_rejected(setup):
    c, pid, s, _ = setup
    line = s.state(pid)["lines"][0]
    review = c.app.state.review
    review.assign(pid, review.state(pid)["revision"], [line["id"]], None)
    with pytest.raises(ValueError, match="未知"):
        s.line(pid, s.state(pid)["revision"], line["id"], True, {})
    with pytest.raises(ValueError):
        s.profile(pid, 999, line["speaker_id"], "one", 180)


def test_audio_rejects_empty_and_wrong_format():
    with pytest.raises(ValueError):
        module.inspect_audio(b"bad")


def test_long_dialogue_maps_audio_to_each_display_frame(setup):
    client, _, speech, _calls = setup
    raw = ("甲曰：「" + "这段话保持原文并且需要按显示框分段。" * 12 + "」").encode()
    pid = client.post(
        "/api/projects", files={"file": ("long.txt", raw)}, data={"rights_status": "owned"}
    ).json()["id"]
    review = client.app.state.review
    state = review.state(pid)
    c, d = state["characters"][0], state["dialogues"][0]
    review.character(pid, state["revision"], c["display_name"], [], "", c["id"])
    review.assign(pid, review.state(pid)["revision"], [d["id"]], c["id"])
    speech.profile(pid, speech.state(pid)["revision"], c["id"], "one", 180)
    speech.line(pid, speech.state(pid)["revision"], d["id"], True, {})
    line = speech.state(pid)["lines"][0]
    assert len(line["segments"]) > 2
    assert "".join(s["original"] for s in line["segments"]) == d["text"]
    assert speech.synthesize(pid, d["id"])["generated"] == len(line["segments"])
    line = speech.state(pid)["lines"][0]
    speech.accept(
        pid,
        speech.state(pid)["revision"],
        d["id"],
        {s["key"]: s["candidate"]["id"] for s in line["segments"]},
    )
    units, _ = review.presentation(pid)
    assert len(speech.for_export(pid, units)[1]) == len(line["segments"])
    assert client.get(f"/api/projects/{pid}/source").content == raw


def test_synthetic_audio_bundle_migrates_and_exports_without_system_voice(
    setup, tmp_path, monkeypatch
):
    c, pid, s, _calls = setup
    for line in s.state(pid)["lines"]:
        s.synthesize(pid, line["id"])
        current = next(l for l in s.state(pid)["lines"] if l["id"] == line["id"])
        s.accept(
            pid,
            s.state(pid)["revision"],
            line["id"],
            {x["key"]: x["candidate"]["id"] for x in current["segments"]},
        )
    archive = c.get(f"/api/projects/{pid}/bundle").content
    original = module.capabilities()
    monkeypatch.setattr(
        module,
        "capabilities",
        lambda: original | {"available": False, "voices": [], "model": "other-os"},
    )
    other = TestClient(create_app(tmp_path / "restored"))
    imported = other.post("/api/project-bundles", files={"file": ("test.zip", archive)})
    assert imported.status_code == 201, imported.text
    restored = imported.json()["id"]
    content = other.get(f"/api/projects/{restored}/reader/content").json()
    sounds = [a for a in content["media"].values() if a["type"] == "audio"]
    assert len(sounds) == 2
    for sound in sounds:
        assert other.get(sound["url"]).status_code == 200
    response = other.post(f"/api/projects/{restored}/reader/exports")
    assert response.status_code == 202
    assert other.get(f"/api/projects/{restored}/jobs").json()[0]["state"] == "completed"
