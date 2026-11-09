import base64
import json
import time
import wave

import pytest
import test_speech as local_fixture


@pytest.fixture
def setup(tmp_path, monkeypatch):
    return local_fixture.setup.__wrapped__(tmp_path, monkeypatch)

from storygal import openai_speech as remote


class Connection:
    def __init__(self, events):
        self.events = iter(events)
        self.sent = []

    def recv(self, **_):
        return json.dumps(next(self.events))

    def send(self, event):
        self.sent.append(json.loads(event))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def events(text="你好。", *, status="completed"):
    return [
        {
            "type": "response.output_audio.delta",
            "delta": base64.b64encode(b"\x10\x10" * 2400).decode(),
        },
        {"type": "response.output_audio_transcript.done", "transcript": text},
        {"type": "response.done", "response": {"status": status}},
    ]


def test_realtime_render_waits_for_session_and_writes_verified_pcm(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setattr(remote, "capabilities", lambda: {"available": True})
    connection = Connection([{"type": "session.created"}, {"type": "session.updated"}, *events()])
    target = tmp_path / "clip.wav"
    result = remote.render(
        "你好。",
        {"voice": "cedar", "speed": 180, "instructions": "沉稳"},
        target,
        connect=lambda *_a, **_k: connection,
    )
    assert result["generated_transcript"] == "你好。"
    assert connection.sent[0]["type"] == "session.update"
    assert connection.sent[1]["response"]["conversation"] == "none"
    assert connection.sent[1]["response"]["input"] == []
    assert "沉稳" in connection.sent[1]["response"]["instructions"]
    with wave.open(str(target)) as clip:
        assert (clip.getnchannels(), clip.getsampwidth(), clip.getframerate()) == (1, 2, 24000)
        assert clip.getnframes() == 2400


@pytest.mark.parametrize(
    "output,status",
    [
        ("你好，我是孔明。", "completed"),
        ("", "completed"),
        ("你好。", "incomplete"),
        ("妳好。", "completed"),
    ],
)
def test_changed_missing_and_incomplete_dialogue_is_rejected(output, status):
    with pytest.raises(ValueError):
        remote.collect(Connection(events(output, status=status)), "你好。", time.monotonic() + 1)


def test_typography_normalization_does_not_allow_extra_or_changed_words():
    assert remote.normalized("「你好！」\n") == remote.normalized("你好。")
    assert remote.normalized("趙雲") != remote.normalized("赵云")


def test_cloud_settings_save_without_key_but_synthesis_does_not_fallback(setup, monkeypatch):
    _, pid, speech, calls = setup
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    line = speech.state(pid)["lines"][0]
    speech.profile(
        pid,
        speech.state(pid)["revision"],
        line["speaker_id"],
        "cedar",
        180,
        remote.PROVIDER,
        "沉稳",
    )
    assert speech.state(pid)["profiles"][line["speaker_id"]]["provider"] == remote.PROVIDER
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        speech.synthesize(pid, line["id"])
    assert not calls
    assert speech.state(pid)["lines"][0]["segments"][0]["candidate"] is None


def test_cloud_cache_isolated_and_delivery_changes_invalidate_only_selected_line(
    setup, monkeypatch
):
    _, pid, speech, local_calls = setup
    for line in speech.state(pid)["lines"]:
        speech.synthesize(pid, line["id"])
        fresh = next(x for x in speech.state(pid)["lines"] if x["id"] == line["id"])
        speech.accept(
            pid,
            speech.state(pid)["revision"],
            line["id"],
            {s["key"]: s["candidate"]["id"] for s in fresh["segments"]},
        )
    first, second = speech.state(pid)["lines"]
    retained = second["segments"][0]["accepted"]["id"]
    monkeypatch.setattr(
        remote,
        "capabilities",
        lambda: {
            "available": True,
            "provider": remote.PROVIDER,
            "model": remote.MODEL,
            "version": 1,
            "format": "pcm_s16le/24000Hz/mono",
            "voices": remote.VOICES,
        },
    )
    cloud_calls = []

    def render(text, profile, target):
        cloud_calls.append((text, profile))
        with wave.open(str(target), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(24000)
            out.writeframes(b"\x10\x10" * 2400)
        return {"generated_transcript": text, "text_check": "matched_typography_normalized"}

    monkeypatch.setattr(remote, "render", render)
    speech.profile(
        pid,
        speech.state(pid)["revision"],
        first["speaker_id"],
        "cedar",
        180,
        remote.PROVIDER,
        "沉稳",
    )
    first = speech.state(pid)["lines"][0]
    assert not first["segments"][0]["accepted"]
    assert speech.synthesize(pid, first["id"])["generated"] == 1
    assert speech.synthesize(pid, first["id"])["reused"] == 1
    speech.line(pid, speech.state(pid)["revision"], first["id"], True, {}, "虚弱")
    assert speech.state(pid)["lines"][0]["segments"][0]["candidate"] is None
    speech.synthesize(pid, first["id"])
    assert "虚弱" in cloud_calls[-1][1]["instructions"]
    assert len(cloud_calls) == 2 and len(local_calls) == 2
    assert speech.state(pid)["lines"][1]["segments"][0]["accepted"]["id"] == retained


def test_vendor_error_is_redacted_and_audio_limit_checked(monkeypatch):
    with pytest.raises(ValueError) as error:
        remote.collect(
            Connection([{"type": "error", "error": {"message": "private-vendor-details"}}]),
            "你好",
            time.monotonic() + 1,
        )
    assert "private-vendor-details" not in str(error.value)
    monkeypatch.setattr(remote, "MAX_AUDIO_BYTES", 2)
    with pytest.raises(ValueError, match="两分钟"):
        remote.collect(Connection(events()), "你好。", time.monotonic() + 1)
