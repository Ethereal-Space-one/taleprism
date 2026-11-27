"""Hand-directed passage ambience; no interpretation, external service or uploaded samples."""

import json
import re
import struct
import uuid
from functools import lru_cache

from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .narration import Decision, canonical_wav
from .passage_audio import PassageAudio
from .soundscape_audio import validate_palette
from .text import sha256

TABLE = "soundscape_takes"
PUBLIC_LABEL = "段落声景"
DURATION = 12
WAV_BYTES = 44 + 24000 * 2 * 2 * DURATION
GENERATOR = "taleprism-procedural-v1"
BIND_FIELDS = (
    "original_sha256 source_sha256 byte_start byte_end paragraph_sha256 evidence_start evidence "
    "generator rain car_at sha256"
)
FIELDS = "id duration status binding_sha256 wind pencil " + BIND_FIELDS


def inspect_wav(raw):
    if len(raw) != WAV_BYTES:
        raise ValueError("声景必须是完整的 12 秒标准 PCM WAV。")
    canonical, duration = canonical_wav(raw)
    if (
        canonical != raw
        or duration != DURATION
        or struct.unpack_from("<HHI", raw, 20) != (1, 2, 24000)
    ):
        raise ValueError("声景必须是 24 kHz 双声道 16 位 PCM，不含附加元数据。")
    return raw, duration


def evidence_position(block, evidence, start):
    if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 300:
        raise ValueError("请选择段内连续的原文引句（1–300 字）。")
    text, quote = block["text"].encode(), evidence.encode()
    if start is None:
        index = text.find(quote)
        if index < 0:
            raise ValueError("引句必须逐字位于所选原文段落内。")
        if text.find(quote, index + 1) != -1:
            raise ValueError("这段原文中有相同引句，请选择具体出现位置。")
        return block["byte_start"] + index
    if type(start) is not int:
        raise ValueError("引句位置必须是原稿的 UTF-8 字节偏移。")
    at = start - block["byte_start"]
    if not 0 <= at <= len(text) - len(quote) or text[at : at + len(quote)] != quote:
        raise ValueError("引句位置不在所选段落或不对应原文。")
    return start


def binding(row):
    payload = ["taleprism-soundscape-v1", *[row[k] for k in BIND_FIELDS.split()]]
    if row.get("wind", False):
        payload.extend(["wind", True])
    if row.get("pencil", False):
        payload.extend(["pencil", True])
    return sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())


def validate_record(row, blocks, source_sha, original_sha, duration):
    if (
        set(row) - {"wind", "pencil"} != set(FIELDS.split()) - {"wind", "pencil"}
        or any(type(row[k]) is not int for k in ("byte_start", "byte_end", "evidence_start"))
        or type(row["duration"]) not in (int, float)
        or row["duration"] != duration
        or duration != DURATION
        or row["generator"] != GENERATOR
        or row["status"] not in ("pending", "accepted", "withdrawn")
        or not isinstance(row["sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
    ):
        raise ValueError("声景的格式、版本或状态无效。")
    validate_palette(row["rain"], row["car_at"], row.get("wind", False), row.get("pencil", False))
    block = blocks.get(row["byte_start"])
    if (
        not block
        or block["byte_end"] != row["byte_end"]
        or row["source_sha256"] != source_sha
        or row["original_sha256"] != original_sha
        or row["paragraph_sha256"] != sha256(block["text"].encode())
        or row["binding_sha256"] != binding(row)
    ):
        raise ValueError("声景与原文段落、创作选择或声音文件不再匹配。")
    evidence_position(block, row["evidence"], row["evidence_start"])


class Soundscapes(PassageAudio):
    table = TABLE
    endpoint = "soundscapes"
    directory = block_key = "soundscape"
    origin = "paragraph_soundscape"
    label = PUBLIC_LABEL
    creator_fields = "evidence evidence_start rain car_at wind pencil"
    max_size = WAV_BYTES
    inspect_wav = staticmethod(inspect_wav)
    validate_record = staticmethod(validate_record)

    def state(self, pid):
        state = super().state(pid)
        for take in state["takes"]:
            take.setdefault("wind", False)
        return state

    def public_cue(self, row):
        if row.get("pencil"):
            label = "铅笔在纸上划过，随后静默"
        elif row.get("wind"):
            label = "风中一辆车驶过" if row["car_at"] is not None else "风声"
        elif row["rain"]:
            label = "细雨中一辆车驶过" if row["car_at"] is not None else "细雨"
        else:
            label = "一辆车驶过"
        return {"description": label}

    def stage(
        self,
        pid,
        revision,
        byte_start,
        evidence,
        evidence_start,
        rain,
        car_at,
        wind=False,
        pencil=False,
    ):
        from .review import ConflictError
        from .soundscape_audio import render_soundscape

        if self.reader.load(pid)[0] != revision:
            raise ConflictError("阅读器配置已更新，请刷新后重试。")
        validate_palette(rain, car_at, wind, pencil)
        block = next((b for b in self.reader.blocks(pid) if b["byte_start"] == byte_start), None)
        if block is None:
            raise ValueError("请选择现有原文段落。")
        start = evidence_position(block, evidence, evidence_start)
        wav, duration = inspect_wav(render_soundscape(rain, car_at, wind=wind, pencil=pencil))
        project = self.store.get(pid)
        row = {
            "id": str(uuid.uuid4()),
            "byte_start": byte_start,
            "byte_end": block["byte_end"],
            "source_sha256": project["canonical_sha256"],
            "original_sha256": project["sha256"],
            "paragraph_sha256": sha256(block["text"].encode()),
            "evidence": evidence,
            "evidence_start": start,
            "generator": GENERATOR,
            "rain": rain,
            "car_at": car_at,
            **({"wind": True} if wind else {}),
            **({"pencil": True} if pencil else {}),
            "duration": duration,
            "sha256": sha256(wav),
            "status": "pending",
        }
        row["binding_sha256"] = binding(row)
        return self.save_pending(pid, revision, row, wav, "soundscape.stage")


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    byte_start: int = Field(ge=0)
    evidence: str = Field(min_length=1, max_length=300)
    evidence_start: int | None = Field(default=None, ge=0)
    rain: bool
    wind: bool = False
    pencil: bool = False
    car_at: int | None = Field(default=None, ge=2, le=10)


def mount_soundscapes(app, reader):
    sound = reader.soundscapes
    prefix = "/api/projects/{pid}/reader/soundscapes"

    @lru_cache(maxsize=1)
    def rain_preview():
        from .soundscape_audio import render_soundscape

        return render_soundscape(True, None)

    @app.get("/api/studio/preview/rain.wav")
    def preview_rain():
        # Fixed, text-free reference: never creates a take, requires no project or model.
        return Response(
            rain_preview(),
            media_type="audio/wav",
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @app.get(prefix)
    def state(pid: str):
        return sound.state(pid)

    @app.post(prefix, status_code=201)
    def stage(pid: str, body: Proposal):
        return sound.stage(pid, **body.model_dump())

    @app.patch(prefix + "/{aid}")
    def decide(pid: str, aid: str, body: Decision):
        return sound.change(pid, body.revision, aid, body.status)

    @app.get(prefix + "/{aid}/file")
    def audition(pid: str, aid: str):
        return FileResponse(
            sound.path(pid, aid), media_type="audio/wav", headers={"Cache-Control": "no-store"}
        )
