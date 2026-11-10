"""Scene continuity declarations and dependency-scoped visual checks, not image recognition."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .text import sha256


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Object(Strict):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["fixed", "movable"] = "movable"
    appearance: str = Field(default="", max_length=500)
    home: str = Field(default="", max_length=500)
    origin: Literal["source", "artistic"] = "artistic"
    evidence: str = Field(default="", max_length=1000)


class Scene(Strict):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=80)
    layout: str = Field(default="", max_length=3000)
    reference_asset_id: str | None = None
    objects: list[Object] = Field(default_factory=list, max_length=32)


class ObjectState(Strict):
    object_id: str
    visibility: Literal["visible", "offscreen", "absent"] = "visible"
    position: str = Field(default="", max_length=500)
    reason: str = Field(default="", max_length=1000)


class Continuity(Strict):
    scene_id: str | None = None
    method: Literal["reuse", "edit", "new_view"] = "edit"
    camera: str = Field(default="", max_length=500)
    changes: str = Field(default="", max_length=2000)
    states: list[ObjectState] = Field(default_factory=list, max_length=32)


class ImageBasis(Strict):
    asset_id: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CharacterBasis(Strict):
    character_id: str = Field(min_length=1)
    figure_asset_id: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def paired_reference(self):
        if bool(self.figure_asset_id) != bool(self.sha256):
            raise ValueError("人物参考编号与哈希必须同时提供。")
        return self


class CheckBasis(Strict):
    version: Literal[1] = 1
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    character_references: list[CharacterBasis] = Field(max_length=768)
    images: list[ImageBasis] = Field(max_length=65)

    @model_validator(mode="after")
    def unique_references(self):
        if len({r.character_id for r in self.character_references}) != len(
            self.character_references
        ):
            raise ValueError("检查依据中的人物重复。")
        if len({r.asset_id for r in self.images}) != len(self.images):
            raise ValueError("检查依据中的图片重复。")
        return self


class Check(Strict):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: Literal["creator", "assistant"]
    notes: str = Field(min_length=8, max_length=2000)
    checked_at: str = Field(min_length=1)
    # Legacy records remain readable, but a missing basis is never a valid pass.
    status: Literal["passed", "rejected", "revoked", "stale"] = "passed"
    basis: CheckBasis | None = None
    invalidated_reason: str | None = Field(default=None, max_length=2000)


def passed(shot):
    check = shot.get("continuity_check")
    return bool(check and check.get("status") == "passed" and check.get("basis"))


def sequence(plan, shot):
    sid = shot["continuity"]["scene_id"]
    return sorted(
        [
            s
            for s in plan["shots"]
            if s["continuity"]["scene_id"] == sid and s["after_byte"] <= shot["after_byte"]
        ],
        key=lambda s: s["after_byte"],
    )


def fingerprint(plan, shot):
    sid = shot["continuity"]["scene_id"]
    data = {
        "style": plan["style"],
        "scene": next((s for s in plan["scenes"] if s["id"] == sid), None),
        "shots": [
            {k: v for k, v in s.items() if k not in {"status", "continuity_check"}}
            for s in (sequence(plan, shot) if sid else [shot])
        ],
    }
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode())


def validate(plan, assets, source, *, for_restore=False):
    scenes = {s["id"]: s for s in plan["scenes"]}
    if len(scenes) != len(plan["scenes"]):
        raise ValueError("场景编号重复。")
    for scene in scenes.values():
        if scene["reference_asset_id"] and scene["reference_asset_id"] not in assets:
            raise ValueError("场景母版图片不属于本项目或已拒绝。")
        if len({o["id"] for o in scene["objects"]}) != len(scene["objects"]):
            raise ValueError("场景物件编号重复。")
        for obj in scene["objects"]:
            if obj["origin"] == "source" and (not obj["evidence"] or obj["evidence"] not in source):
                raise ValueError("原文物件需填写逐字依据；美术补充请选择艺术设计。")
    for shot in sorted(plan["shots"], key=lambda s: s["after_byte"]):
        c = shot["continuity"]
        if not c["scene_id"]:
            if c["states"] or shot["continuity_check"]:
                raise ValueError("物件状态与检查记录必须绑定场景。")
            continue
        if c["scene_id"] not in scenes:
            raise ValueError("镜头引用的场景不存在。")
        scene = scenes[c["scene_id"]]
        objects = {o["id"]: o for o in scene["objects"]}
        states = {s["object_id"]: s for s in c["states"]}
        if len(states) != len(c["states"]) or not set(states) <= set(objects):
            raise ValueError("镜头物件状态重复或引用未知物件。")
        complete = shot["status"] == "approved" or passed(shot)
        if complete and (
            set(states) != set(objects)
            or not objects
            or not scene["layout"].strip()
            or not c["camera"].strip()
            or not c["changes"].strip()
        ):
            raise ValueError("确认前请填写场景布局、机位、允许变化及全部物件状态。")
        prior = sequence(plan, shot)[:-1]
        previous = {s["object_id"]: s for s in prior[-1]["continuity"]["states"]} if prior else {}
        for oid, state in states.items():
            obj = objects[oid]
            if complete and not state["position"].strip():
                raise ValueError("请交代物件所在位置或尚未出现的状态。")
            if obj["kind"] == "fixed" and (
                state["visibility"] == "absent"
                or state["position"] != obj["home"]
                or not obj["home"].strip()
            ):
                raise ValueError("固定物件不能消失或移动；画面未拍到时请选择画外并保留位置。")
            prev = previous.get(oid)
            if (
                complete
                and prev
                and any(prev[k] != state[k] for k in ["position", "visibility"])
                and not state["reason"].strip()
            ):
                raise ValueError("物件位置或可见性发生变化，请交代变化理由。")
        check = shot["continuity_check"]
        if (
            check
            and check["status"] == "passed"
            and not for_restore
            and (
                not check["basis"]
                or shot["status"] != "approved"
                or check["fingerprint"] != fingerprint(plan, shot)
                or not shot["image_asset_id"]
                or not scene["reference_asset_id"]
                or any(not passed(s) for s in prior)
            )
        ):
            raise ValueError("连续性检查已失效或缺少母版／前序检查，请按顺序重新检查。")


def context(plan, shot):
    scene = next((s for s in plan["scenes"] if s["id"] == shot["continuity"]["scene_id"]), None)
    if not scene:
        return None
    previous = sequence(plan, shot)[:-1]
    prior = previous[-1] if previous else None
    return {
        "scene": scene,
        "current": shot["continuity"],
        "previous_shot_id": prior["id"] if prior else None,
        "previous_states": prior["continuity"]["states"] if prior else [],
        "previous_image_asset_id": prior["image_asset_id"] if prior and passed(prior) else None,
        "previous_check_required": bool(prior and not passed(prior)),
        "rule": "固定物件保持物理位置与结构。画外不等于消失。只有changes与states明确说明的变化允许发生。母版、前序图片和当前人物参考共同核对；不可用前序错误替代母版。",
    }
