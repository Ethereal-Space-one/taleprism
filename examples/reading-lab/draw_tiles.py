"""Rebuild the two geometric calibration images; standard library only."""

import zlib
from pathlib import Path
from struct import pack

ROOT = Path(__file__).resolve().parent


def png(name, pixel):
    def chunk(tag, data):
        return pack(">I", len(data)) + tag + data + pack(">I", zlib.crc32(tag + data))

    width, height = 640, 384
    rows = b"".join(
        b"\0" + bytes(c for x in range(width) for c in pixel(x, y))
        for y in range(height)
    )
    (ROOT / name / "plate.png").write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def proof(x, y):
    if 60 <= x < 580 and 88 <= y < 298:
        k = (x - 60) // 104
        return (
            (45, 100, 116),
            (198, 91, 68),
            (225, 183, 84),
            (128, 153, 128),
            (28, 45, 58),
        )[k]
    return 236, 232, 214


def grid(x, y):
    if x < 326:
        return (
            (49, 63, 73)
            if x in range(40, 48) or y in range(183, 191)
            else (226, 215, 182)
        )
    if x % 54 < 3 or y % 54 < 3:
        return 93, 135, 155
    return 55, 80, 94


if __name__ == "__main__":
    png("proof-strip", proof)
    png("rain-grid", grid)
