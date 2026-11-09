"""Immutable source decoding, byte ranges and display pagination (no AI involved)."""

import hashlib
import re

from pydantic import BaseModel

MAX_BYTES = 2_000_000
MAX_CHARS = 30_000
PAGE_CHARS = 64


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Span(BaseModel):
    id: int
    byte_start: int
    byte_end: int
    kind: str
    text: str


class DisplayUnit(BaseModel):
    id: int
    byte_start: int
    byte_end: int
    text: str
    speaker_id: str | None = None


def decode_source(raw: bytes, encoding: str = "auto") -> tuple[str, bytes]:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("请选择非空 TXT 文件，文件不能超过 2 MB。")
    if encoding not in {"auto", "utf-8", "gb18030"}:
        raise ValueError("编码仅支持自动、UTF-8 或 GB18030。")
    candidates = ["utf-8", "gb18030"] if encoding == "auto" else [encoding]
    for candidate in candidates:
        try:
            text = raw.decode(candidate, errors="strict")
            if text.encode(candidate, errors="strict") != raw:
                continue
        except (UnicodeError, LookupError):
            continue
        if any(ord(c) < 32 and c not in "\r\n\t" for c in text):
            raise ValueError("文件包含不支持的控制字符，请使用纯文本 TXT。")
        if not text.lstrip("\ufeff").strip():
            raise ValueError("文本中没有可显示的内容。")
        if len(text) > MAX_CHARS:
            raise ValueError("P0 每个项目最多接收 30,000 个字符，请按章拆分。")
        return candidate, text.encode("utf-8")
    raise ValueError("无法无损读取文件，请手动选择正确编码，或保存为 UTF-8 TXT。")


def split_spans(data: bytes) -> list[Span]:
    text = data.decode("utf-8")
    # The regex consumes every code point, including BOM, indentation and line breaks.
    pieces = re.findall(
        r"\s+|\ufeff|[「」『』“”\"]|[^\s\ufeff「」『』“”\"。！？!?；;]+[。！？!?；;]?|[。！？!?；;]",
        text,
    )
    spans: list[Span] = []
    offset = 0
    quote_stack: list[str] = []
    closers = {"「": "」", "『": "』", "“": "”", '"': '"'}
    for index, piece in enumerate(pieces):
        end = offset + len(piece.encode("utf-8"))
        if piece.isspace() or piece == "\ufeff":
            kind = "whitespace"
        elif piece in {"「", "」", "『", "』", "“", "”", '"'}:
            kind = "quote"
            if quote_stack and piece == quote_stack[-1]:
                quote_stack.pop()
            elif piece in closers:
                quote_stack.append(closers[piece])
        else:
            kind = "dialogue" if quote_stack else "narration"
        spans.append(Span(id=index, byte_start=offset, byte_end=end, kind=kind, text=piece))
        offset = end
    assert_span_coverage(data, spans)
    return spans


def assert_span_coverage(data: bytes, spans: list[Span]) -> None:
    offset = 0
    for span in spans:
        if span.byte_start != offset or span.byte_end <= offset:
            raise ValueError("原文切分存在遗漏或重叠。")
        if data[span.byte_start : span.byte_end] != span.text.encode("utf-8"):
            raise ValueError("标注与原文不一致。")
        offset = span.byte_end
    if offset != len(data) or b"".join(s.text.encode("utf-8") for s in spans) != data:
        raise ValueError("原文回拼失败。")


def visible_text(text: str) -> str:
    """Remove only initial BOM, line separators and per-line indentation/trailing blanks."""
    return "".join(
        line.strip(" \t\u3000") for line in re.split(r"\r\n|\r|\n", text.removeprefix("\ufeff"))
    )


def build_units(data: bytes, limit: int = PAGE_CHARS) -> list[DisplayUnit]:
    if limit < 2:
        raise ValueError("显示容量过小。")
    units: list[DisplayUnit] = []
    offset = 0
    for line in re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", data.decode("utf-8")):
        if not line:
            continue
        body = line.rstrip("\r\n")
        bom = 1 if offset == 0 and body.startswith("\ufeff") else 0
        start = len(body) - len(body[bom:].lstrip(" \t\u3000"))
        stop = len(body.rstrip(" \t\u3000"))
        cursor = start
        while cursor < stop:
            end = min(cursor + limit, stop)
            if end < stop:
                # Prefer sentence boundaries without dropping punctuation or cutting surrogate pairs.
                candidates = [
                    i + 1 for i in range(cursor + limit // 2, end) if body[i] in "。！？!?；;，,」”"
                ]
                if candidates:
                    end = candidates[-1]
            chunk = body[cursor:end]
            byte_start = offset + len(body[:cursor].encode("utf-8"))
            units.append(
                DisplayUnit(
                    id=len(units),
                    byte_start=byte_start,
                    byte_end=byte_start + len(chunk.encode("utf-8")),
                    text=chunk,
                )
            )
            cursor = end
        offset += len(line.encode("utf-8"))
    if "".join(unit.text for unit in units) != visible_text(data.decode("utf-8")):
        raise ValueError("显示单元与原文内容不一致。")
    return units
