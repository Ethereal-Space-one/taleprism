"""Local macOS speech adapter and immutable, parameter-addressed audio takes."""

import io
import json
import platform
import re
import shutil
import subprocess
import tempfile
import uuid
import wave
from functools import lru_cache
from pathlib import Path

from . import openai_speech
from .review import ConflictError, Review
from .storage import now
from .text import sha256


@lru_cache(maxsize=1)
def voices() -> list[str]:
    if platform.system() != "Darwin" or not Path("/usr/bin/say").exists():
        return []
    result = subprocess.run(
        ["/usr/bin/say", "-v", "?"], capture_output=True, text=True, timeout=15, check=False
    )
    return list(
        dict.fromkeys(
            [
                m[1].strip()
                for line in result.stdout.splitlines()
                if (m := re.match(r"^(.*?)\s+zh_(?:CN|TW|HK)\s+", line))
            ]
        )
    )


def capabilities() -> dict:
    available = voices()
    return {
        "provider": "macos-say",
        "model": platform.mac_ver()[0],
        "voices": available,
        "available": bool(available and shutil.which("ffmpeg")),
        "speed_min": 100,
        "speed_max": 300,
        "emotions": False,
        "cloning": False,
        "remote": False,
        "format": "pcm_s16le/24000Hz/mono",
        "version": 1,
    }


def inspect_audio(content: bytes) -> float:
    try:
        with wave.open(io.BytesIO(content), "rb") as audio:
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != 24000
            ):
                raise ValueError("音频格式不符合导出要求。")
            frames = audio.getnframes()
            data = audio.readframes(frames)
            if not frames or len(data) != frames * 2 or not any(data):
                raise ValueError("音频为空或已损坏。")
            duration = frames / 24000
            if duration > 120:
                raise ValueError("单段音频超过两分钟，请缩短读音修正。")
            return duration
    except (wave.Error, EOFError):
        raise ValueError("音频无法解码。") from None


def render(text: str, voice: str, speed: int, destination: Path):
    with tempfile.TemporaryDirectory(prefix="storygal-tts-") as temp:
        aiff = Path(temp) / "speech.aiff"
        try:
            # Disable Apple embedded speech directives; display/source text is never changed.
            spoken = text.replace("[[", "[ [").replace("]]", "] ]")
            subprocess.run(
                ["/usr/bin/say", "-v", voice, "-r", str(speed), "-o", str(aiff), "-f", "-"],
                input=spoken,
                text=True,
                capture_output=True,
                timeout=60,
                check=True,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(aiff),
                    "-ac",
                    "1",
                    "-ar",
                    "24000",
                    "-c:a",
                    "pcm_s16le",
                    str(destination),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
            inspect_audio(destination.read_bytes())
        except (OSError, subprocess.SubprocessError):
            raise ValueError("本机语音合成失败或超时，请检查音色是否已安装，并重试此句。") from None


class Speech:
    def __init__(self, store, review: Review):
        self.store, self.review = store, review
        with store.db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS speech_states(project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS speech_takes(project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id));
            """)

    def load(self, pid):
        self.store.get(pid)
        with self.store.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO speech_states VALUES (?,0,?)",
                (pid, json.dumps({"profiles": {}, "lines": {}})),
            )
            row = db.execute(
                "SELECT revision,data FROM speech_states WHERE project_id=?", (pid,)
            ).fetchone()
        return row[0], json.loads(row[1])

    def mutate(self, pid, revision, action, fn):
        self.load(pid)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision,data FROM speech_states WHERE project_id=?", (pid,)
            ).fetchone()
            if row[0] != revision:
                raise ConflictError("配音设置已更新，请刷新后再保存。")
            data = json.loads(row[1])
            before = json.loads(row[1])
            fn(data)
            db.execute(
                "UPDATE speech_states SET revision=revision+1,data=? WHERE project_id=?",
                (json.dumps(data, ensure_ascii=False), pid),
            )
            self.review.audit(db, pid, action, before, data)

    def profile(self, pid, revision, cid, voice, speed, provider="macos-say", instructions=""):
        state = self.review.state(pid)
        if not any(c["id"] == cid and c["status"] == "confirmed" for c in state["characters"]):
            raise ValueError("请先确认角色身份。")
        if provider not in {"macos-say", openai_speech.PROVIDER}:
            raise ValueError("未知配音后端。")
        available_voices = openai_speech.VOICES if provider == openai_speech.PROVIDER else voices()
        if voice not in available_voices or not 100 <= speed <= 300:
            raise ValueError("音色或语速不受所选配音方式支持。")
        if len(instructions) > 1000 or (provider == "macos-say" and instructions):
            raise ValueError("本机语音不支持表演说明；云端说明最多 1000 字。")
        profile = {"voice": voice, "speed": speed}
        if provider == openai_speech.PROVIDER:
            profile.update(
                provider=provider, model=openai_speech.MODEL, instructions=instructions.strip()
            )
        self.mutate(
            pid,
            revision,
            "speech.profile",
            lambda d: d["profiles"].update({cid: profile}),
        )

    def line(self, pid, revision, did, selected, overrides, instructions=None):
        state = self.review.state(pid)
        dialogue = next((d for d in state["dialogues"] if d["id"] == did), None)
        if not dialogue:
            raise KeyError()
        if selected and (
            dialogue["status"] != "reviewed"
            or not any(
                c["id"] == dialogue["speaker_id"] and c["status"] == "confirmed"
                for c in state["characters"]
            )
        ):
            raise ValueError("未知说话人或未审核对白不能自动配音，请先确认归属。")
        if any(
            not t.strip() or len(t) > 500 or any(ord(c) < 32 and c not in "\n\t" for c in t)
            for t in overrides.values()
        ):
            raise ValueError("读音修正需为 1–500 个字符。")
        valid = {
            s["key"] for s in self.state(pid)["lines"] if s["id"] == did for s in s["segments"]
        }
        if not set(overrides) <= valid:
            raise ValueError("读音片段已变化，请刷新后重新修正。")
        if instructions is not None and len(instructions) > 1000:
            raise ValueError("逐句表演说明最多 1000 字。")

        def update(data):
            old = data["lines"].get(did, {})
            data["lines"][did] = old | {"selected": selected, "overrides": overrides}
            if instructions is not None:
                data["lines"][did]["instructions"] = instructions.strip()

        self.mutate(pid, revision, "speech.line", update)

    def state(self, pid):
        revision, config = self.load(pid)
        units, review = self.review.presentation(pid)
        canonical = self.review.source(pid)
        caps = capabilities()
        remote_caps = openai_speech.capabilities()
        with self.store.db() as db:
            # A speaker change revokes acceptance and advances this revision in
            # one transaction. Never combine an old acceptance map with new review.
            current_revision = db.execute(
                "SELECT revision FROM speech_states WHERE project_id=?", (pid,)
            ).fetchone()[0]
            if current_revision != revision:
                raise ConflictError("配音设置已更新，请刷新后再读取。")
            takes = self.review.rows(db, "speech_takes", pid)
        lines = []
        for d in review["dialogues"]:
            settings = config["lines"].get(d["id"], {})
            profile = config["profiles"].get(d["speaker_id"])
            line_caps = (
                remote_caps
                if profile and profile.get("provider") == openai_speech.PROVIDER
                else caps
            )
            effective = profile
            if profile and profile.get("provider") == openai_speech.PROVIDER:
                effective = profile | {
                    "instructions": "\n".join(
                        filter(None, [profile.get("instructions"), settings.get("instructions")])
                    )
                }
            character = next(
                (
                    c
                    for c in review["characters"]
                    if c["id"] == d["speaker_id"] and c["status"] == "confirmed"
                ),
                None,
            )
            segments = []
            for unit in units:
                start, end = (
                    max(unit["byte_start"], d["byte_start"]),
                    min(unit["byte_end"], d["byte_end"]),
                )
                if start >= end:
                    continue
                key = f"{start}:{end}"
                original = canonical[start:end].decode()
                spoken = settings.get("overrides", {}).get(key, original)
                spec = {
                    "text": spoken,
                    "character_id": d["speaker_id"],
                    "profile": effective,
                    "provider": line_caps["provider"],
                    "model": line_caps["model"],
                    "version": line_caps["version"],
                    "format": line_caps["format"],
                }
                cache_key = sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True).encode())
                candidates = [t for t in takes if t["cache_key"] == cache_key]
                accepted_id = settings.get("accepted", {}).get(key)
                accepted = next((t for t in candidates if t["id"] == accepted_id), None)
                # Imported, already recorded audio can play on another OS. New synthesis
                # keeps using the current provider/model cache; Review clears acceptance
                # transactionally on speaker changes, even for identical voice profiles.
                if accepted is None and accepted_id:
                    accepted = next(
                        (
                            t
                            for t in takes
                            if t["id"] == accepted_id
                            and t.get("imported")
                            and t.get("text_sha256") == sha256(spoken.encode())
                            and t.get("profile") == effective
                            and t.get("provider") == line_caps["provider"]
                        ),
                        None,
                    )
                segments.append(
                    {
                        "key": key,
                        "unit_id": unit["id"],
                        "byte_start": start,
                        "byte_end": end,
                        "original": original,
                        "spoken": spoken,
                        "cache_key": cache_key,
                        "candidate": candidates[-1] if candidates else None,
                        "accepted": accepted,
                    }
                )
            lines.append(
                {
                    "id": d["id"],
                    "text": d["text"],
                    "speaker_id": d["speaker_id"],
                    "speaker_name": character["display_name"] if character else None,
                    "eligible": bool(character and d["status"] == "reviewed"),
                    "selected": settings.get("selected", False),
                    "profile": profile,
                    "effective_profile": effective,
                    "capabilities": line_caps,
                    "instructions": settings.get("instructions", ""),
                    "overrides": settings.get("overrides", {}),
                    "segments": segments,
                }
            )
        return {
            "revision": revision,
            "review_revision": review["revision"],
            "profiles": config["profiles"],
            "lines": lines,
            "capabilities": caps,
            "providers": [caps | {"label": "本机中文语音"}, remote_caps],
        }

    def path(self, pid, take):
        path = self.store.project_dir(pid) / "audio" / (take["id"] + ".wav")
        if not path.exists() or sha256(path.read_bytes()) != take["sha256"]:
            raise ValueError("音频缺失或哈希不一致，请重做该片段。")
        inspect_audio(path.read_bytes())
        return path

    def synthesize(self, pid, did, segment_key=None, force=False):
        state = self.state(pid)
        line = next((d for d in state["lines"] if d["id"] == did), None)
        if not line or not line["selected"] or not line["eligible"] or not line["profile"]:
            raise ValueError("请勾选已确认角色的对白，并绑定音色。")
        if segment_key and not any(s["key"] == segment_key for s in line["segments"]):
            raise ValueError("片段不存在，请刷新。")
        generated, reused = 0, 0
        for segment in line["segments"]:
            if segment_key and segment["key"] != segment_key:
                continue
            if not force and segment["candidate"]:
                self.path(pid, segment["candidate"])
                reused += 1
                continue
            if not line["capabilities"]["available"]:
                raise ValueError(
                    line["capabilities"].get("reason")
                    or "本机语音后端不可用，请检查 macOS 音色和 ffmpeg。"
                )
            take_id = str(uuid.uuid4())
            directory = self.store.project_dir(pid) / "audio"
            directory.mkdir(exist_ok=True)
            target = directory / (take_id + ".wav")
            try:
                metadata = {}
                if line["profile"].get("provider") == openai_speech.PROVIDER:
                    metadata = openai_speech.render(
                        segment["spoken"], line["effective_profile"], target
                    )
                else:
                    render(
                        segment["spoken"],
                        line["profile"]["voice"],
                        line["profile"]["speed"],
                        target,
                    )
                content = target.read_bytes()
                take = {
                    "id": take_id,
                    "cache_key": segment["cache_key"],
                    "sha256": sha256(content),
                    "duration": inspect_audio(content),
                    "created_at": now(),
                    "profile": line["effective_profile"],
                    "provider": line["capabilities"]["provider"],
                    "model": line["capabilities"]["model"],
                    **metadata,
                    "text_sha256": sha256(segment["spoken"].encode()),
                    "url": f"/api/projects/{pid}/speech/takes/{take_id}",
                }
                target.chmod(0o444)
                with self.store.db() as db:
                    self.review.put(db, "speech_takes", pid, take)
                generated += 1
            except Exception:
                target.unlink(missing_ok=True)
                raise
        return {"generated": generated, "reused": reused}

    def accept(self, pid, revision, did, take_ids):
        state = self.state(pid)
        if revision != state["revision"]:
            raise ConflictError("配音设置已更新，请刷新后再接受。")
        line = next((d for d in state["lines"] if d["id"] == did), None)
        if not line or not line["selected"] or not line["eligible"]:
            raise ValueError("请先选择已确认归属的对白。")
        for segment in line["segments"]:
            with self.store.db() as db:
                take = self.review.item(db, "speech_takes", pid, take_ids.get(segment["key"], ""))
            if take["cache_key"] != segment["cache_key"]:
                raise ValueError("音频与当前读音或音色不匹配，请重新合成。")
            self.path(pid, take)

        def update(data):
            data["lines"][did]["accepted"] = take_ids

        self.mutate(pid, revision, "speech.accept", update)

    def for_export(self, pid, units):
        state = self.state(pid)
        audio = {}
        for line in state["lines"]:
            if not line["selected"]:
                continue
            if not line["eligible"] or not line["profile"]:
                raise ValueError("选中配音的对白归属或音色已失效，请在配音页修正或取消勾选。")
            for segment in line["segments"]:
                take = segment["accepted"]
                if not take:
                    raise ValueError("选中对白还有未接受或已过期的音频，请在配音页完成试听确认。")
                self.path(pid, take)
                if segment["unit_id"] in audio:
                    raise ValueError("同一显示框存在多条配音，请先确认所有对白归属。")
                audio[segment["unit_id"]] = take
        for unit in units:
            if unit["id"] in audio:
                unit["vocal_id"] = audio[unit["id"]]["id"]
        return state, audio
