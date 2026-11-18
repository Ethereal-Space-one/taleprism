"""Bounded, declarative illustration motion and its immutable source/media bindings.

``reviewed`` is the creator's attestation about this direction, not an image,
continuity or publication approval. Unreviewed directions remain editable drafts.
"""

from typing import Annotated, Literal

from PIL import Image
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .text import sha256

Coordinate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]
Point = Annotated[list[Coordinate], Field(min_length=2, max_length=2)]


def simple_polygon(points):
    """Implicitly closed simple masks only: no zero area, holes or crossed edges."""
    epsilon = 1e-10

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_segment(a, b, p):
        return (
            abs(cross(a, b, p)) < epsilon
            and min(a[0], b[0]) - epsilon <= p[0] <= max(a[0], b[0]) + epsilon
            and min(a[1], b[1]) - epsilon <= p[1] <= max(a[1], b[1]) + epsilon
        )

    def intersects(a, b, c, d):
        ab_c, ab_d, cd_a, cd_b = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
        return (ab_c * ab_d < 0 and cd_a * cd_b < 0) or any(
            (on_segment(a, b, c), on_segment(a, b, d), on_segment(c, d, a), on_segment(c, d, b))
        )

    edges = list(zip(points, points[1:] + points[:1]))
    if (
        len({tuple(p) for p in points}) != len(points)
        or abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in edges)) <= 1e-8
    ):
        raise ValueError("动效区域须为不重复顶点且面积非零的多边形，末点无需重复首点。")
    for i, (a, b) in enumerate(edges):
        if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 < 1e-16:
            raise ValueError("动效区域相邻顶点过近。")
        c = points[(i + 2) % len(points)]
        if (
            abs(cross(a, b, c)) <= epsilon
            and ((a[0] - b[0]) * (c[0] - b[0]) + (a[1] - b[1]) * (c[1] - b[1])) > 0
        ):
            raise ValueError("动效区域边界不可折返重叠。")
        for j, (c, d) in enumerate(edges[i + 1 :], i + 1):
            if j == i + 1 or (i == 0 and j == len(edges) - 1):
                continue
            if intersects(a, b, c, d):
                raise ValueError("动效区域边界不可自相交或相触。")
    return points


Polygon = Annotated[list[Point], Field(min_length=3, max_length=64), AfterValidator(simple_polygon)]
Polygons = Annotated[list[Polygon], Field(min_length=1, max_length=8)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class MotionBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    image_sha256: Digest
    source_sha256: Digest
    width: int = Field(ge=1, le=8192)
    height: int = Field(ge=1, le=8192)
    after_byte: int = Field(ge=0)
    evidence: str = Field(min_length=8, max_length=300)
    note: str = Field(min_length=8, max_length=300)
    reviewed: bool

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("动效版本必须为整数 1。")
        return value

    @field_validator("evidence", "note")
    @classmethod
    def meaningful_text(cls, value):
        if sum(not (char.isspace() or char == "\ufeff") for char in value) < 8:
            raise ValueError("动效原文依据与观察说明至少需要 8 个非空白字符。")
        return value

    @model_validator(mode="after")
    def image_budget(self):
        if self.width * self.height > 24_000_000:
            raise ValueError("动效图片像素总数超过限制。")
        return self


class RainMotion(MotionBinding):
    effect: Literal["rain-wet-ground"]
    areas: Polygons
    ground: list[Polygon] = Field(max_length=8)
    drops: int = Field(ge=1, le=128)
    rings: int = Field(ge=0, le=16)

    @model_validator(mode="after")
    def wet_ground(self):
        if self.rings and not self.ground:
            raise ValueError("雨滴涟漪需要明确标记湿地区域；未标记时请将涟漪数量设为 0。")
        return self


class ShoreHit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    x: Coordinate
    phase: float = Field(ge=0, le=8, allow_inf_nan=False)
    length: float = Field(ge=6.5, le=20, allow_inf_nan=False)
    gain: float = Field(ge=0, le=1.3, allow_inf_nan=False)


class ShoreMotion(MotionBinding):
    effect: Literal["wave-impact-backwash"]
    water: Polygons
    bank: list[Point] = Field(min_length=2, max_length=64)
    hits: list[ShoreHit] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def shoreline(self):
        if any(a[0] >= b[0] for a, b in zip(self.bank, self.bank[1:])):
            raise ValueError("岸线的横坐标必须严格递增。")
        if any(not self.bank[0][0] <= hit.x <= self.bank[-1][0] for hit in self.hits):
            raise ValueError("浪击位置必须位于岸线范围内。")
        return self


IllustrationMotion = Annotated[RainMotion | ShoreMotion, Field(discriminator="effect")]


def validate_binding(reader, pid, illustration, asset):
    """Also validate direct/internal saves and restored records, not just API bodies."""
    raw_motion = illustration.get("motion")
    if raw_motion is None:
        return
    # Do not coerce legacy titles, prose or generic presentation data into motion.
    if not isinstance(raw_motion, dict):
        raise ValueError("插图动效必须为结构化配置。")  # noqa: TRY004 -- API validation failure.
    if raw_motion.get("effect") == "rain-wet-ground":
        motion = RainMotion.model_validate(raw_motion)
    elif raw_motion.get("effect") == "wave-impact-backwash":
        motion = ShoreMotion.model_validate(raw_motion)
    else:
        raise ValueError("未知插图动效。")
    source = reader.review.source(pid)
    if motion.after_byte != illustration["after_byte"]:
        raise ValueError("动效绑定的插图位置已改变，请重新核对动效。")
    if motion.source_sha256 != sha256(source):
        raise ValueError("动效绑定的原文已改变，请重新核对。")
    if motion.image_sha256 != asset["sha256"]:
        raise ValueError("动效绑定的图片已改变，请移除或重新核对动效。")
    # Metadata supplied by an importer is not proof of actual image dimensions.
    with Image.open(reader.path(pid, asset["id"])) as image:
        if image.size != (motion.width, motion.height):
            raise ValueError("动效绑定的图片尺寸不匹配，请重新核对。")
    if motion.evidence.encode("utf-8") not in source[: illustration["after_byte"]]:
        raise ValueError("动效依据必须逐字来自插图位置之前的原文。")
