"""Locally uploaded paragraph recordings. Independent of dialogue, speakers and synthesis."""

import re
import struct
import uuid
from typing import Annotated, Literal

from fastapi import File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .passage_audio import PassageAudio
from .text import sha256

MAX_BYTES = 24_000_000
MAX_SECONDS = 120
TABLE = "narration_takes"
FIELDS = "id byte_start byte_end original_sha256 source_sha256 paragraph_sha256 sha256 binding_sha256 duration credit publish_credit status"
PUBLIC_LABEL = "段落朗读"


def canonical_wav(raw):
    """Accept interleaved PCM16, preserve its samples, drop filenames, tags and other chunks."""
    if (
        not 44 <= len(raw) <= MAX_BYTES
        or raw[:4] != b"RIFF"
        or raw[8:12] != b"WAVE"
        or int.from_bytes(raw[4:8], "little") != len(raw) - 8
    ):
        raise ValueError("请提供完整 PCM WAV，文件最多 24 MB。")
    fmt = data = None
    pos = 12
    while pos < len(raw):
        if len(raw) - pos < 8:
            raise ValueError("WAV 文件被截断。")
        tag = raw[pos : pos + 4]
        length = int.from_bytes(raw[pos + 4 : pos + 8], "little")
        left = pos + 8
        right = left + length
        pos = right + length % 2
        if pos > len(raw):
            raise ValueError("WAV 数据区不完整。")
        if tag == b"fmt ":
            if (
                fmt is not None
                or length not in (16, 18)
                or (length == 18 and raw[right - 2 : right] != b"\0\0")
            ):
                raise ValueError("WAV 格式头无效。")
            fmt = struct.unpack_from("<HHIIHH", raw, left)
        elif tag == b"data":
            if data is not None:
                raise ValueError("WAV 数据区重复。")
            data = memoryview(raw)[left:right]
    if fmt is None or data is None or not data:
        raise ValueError("WAV 缺少格式或有效声音。")
    codec, channels, rate, bytes_per_second, alignment, bits = fmt
    if (
        codec != 1
        or bits != 16
        or channels not in (1, 2)
        or not 16000 <= rate <= 48000
        or alignment != 2 * channels
        or bytes_per_second != rate * alignment
        or len(data) % alignment
    ):
        raise ValueError("支持 16 位 PCM WAV、单声道或双声道、采样率 16–48 kHz。")
    duration = len(data) / bytes_per_second
    if duration > MAX_SECONDS or not any(data):
        raise ValueError("朗读不得全为静音，最长 120 秒。")
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        *fmt,
        b"data",
        len(data),
    )
    # Canonical maker/reader assets are the common path. Inspect without making
    # a second in-memory copy of a long stereo recording.
    return (raw if raw[:44] == header and len(raw) == 44 + len(data) else header + data), duration


def binding(row):
    # Ties even repeated identical paragraphs to the exact original location.
    return sha256(
        (
            "\0".join(
                [
                    "taleprism-narration-v1",
                    row["original_sha256"],
                    row["source_sha256"],
                    str(row["byte_start"]),
                    str(row["byte_end"]),
                    row["paragraph_sha256"],
                    row["sha256"],
                ]
            )
        ).encode()
    )


def validate_record(row, blocks, source_sha, original_sha, duration):
    """Validate every restored take, including pending/withdrawn, before publishing a project."""
    if (
        set(row) != set(FIELDS.split())
        or type(row["byte_start"]) is not int
        or type(row["byte_end"]) is not int
        or not isinstance(row["credit"], str)
        or not 1 <= len(row["credit"]) <= 200
        or row["credit"] != row["credit"].strip()
        or type(row["publish_credit"]) is not bool
        or row["status"] not in ("pending", "accepted", "withdrawn")
        or type(row["duration"]) not in (int, float)
        or row["duration"] != duration
        or not isinstance(row["sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
    ):
        raise ValueError("段落朗读记录、来源或时长无效。")
    block = blocks.get(row["byte_start"])
    if (
        not block
        or row["byte_end"] != block["byte_end"]
        or row["source_sha256"] != source_sha
        or row["original_sha256"] != original_sha
        or sha256(block["text"].encode()) != row["paragraph_sha256"]
        or row["binding_sha256"] != binding(row)
    ):
        raise ValueError("朗读绑定与原文、段落位置或音频指纹不一致。")


class Narrations(PassageAudio):
    table = TABLE
    endpoint = "narrations"
    directory = block_key = "narration"
    origin = "paragraph_narration"
    label = PUBLIC_LABEL
    creator_fields = "credit publish_credit"
    max_size = MAX_BYTES
    inspect_wav = staticmethod(canonical_wav)
    validate_record = staticmethod(validate_record)

    def public_credit(self, row):
        return {"credit": row["credit"]} if row["publish_credit"] else {}

    def upload(self, pid, revision, start, credit, publish_credit, raw):
        if not 1 <= len(credit.strip()) <= 200:
            raise ValueError("请填写 1–200 字的录音来源或署名。")
        blocks = self.reader.blocks(pid)
        block = next((b for b in blocks if b["byte_start"] == start), None)
        if block is None:
            raise ValueError("请选择一个现有原文段落，不能使用段内或旧段落偏移。")
        normalized, duration = canonical_wav(raw)
        aid = str(uuid.uuid4())
        project = self.store.get(pid)
        row = {
            "id": aid,
            "byte_start": start,
            "byte_end": block["byte_end"],
            "source_sha256": project["canonical_sha256"],
            "original_sha256": project["sha256"],
            "paragraph_sha256": sha256(block["text"].encode()),
            "sha256": sha256(normalized),
            "duration": duration,
            "credit": credit.strip(),
            "publish_credit": publish_credit,
            "status": "pending",
        }
        row["binding_sha256"] = binding(row)
        return self.save_pending(pid, revision, row, normalized, "narration.upload")


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    status: Literal["accepted", "withdrawn"]


def mount_narrations(app, reader):
    narr = reader.narrations
    prefix = "/api/projects/{pid}/reader/narrations"

    @app.get(prefix)
    def state(pid: str):
        return narr.state(pid)

    @app.post(prefix, status_code=201)
    async def upload(
        pid: str,
        revision: Annotated[int, Form(ge=0)],
        byte_start: Annotated[int, Form(ge=0)],
        credit: Annotated[str, Form(min_length=1, max_length=200)],
        file: Annotated[UploadFile, File()],
        publish_credit: Annotated[bool, Form()] = False,
    ):
        return narr.upload(
            pid, revision, byte_start, credit, publish_credit, await file.read(MAX_BYTES + 1)
        )

    @app.patch(prefix + "/{aid}")
    def decide(pid: str, aid: str, body: Decision):
        return narr.change(pid, body.revision, aid, body.status)

    @app.get(prefix + "/{aid}/file")
    def audition(pid: str, aid: str):
        return FileResponse(
            narr.path(pid, aid), media_type="audio/wav", headers={"Cache-Control": "no-store"}
        )
