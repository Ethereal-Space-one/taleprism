"""Illustrated chapter plates: reviewed local artwork with explicit source placement."""

import copy
import json
import uuid

from PIL import Image

from .reader import REPO
from .reader_casting import expanded_chibi
from .text import sha256

ROOT = REPO / "samples/reader/narrative-v1"


def catalog():
    return json.loads((ROOT / "prompts.json").read_text())["images"]


def import_candidates(reader, pid, revision):
    if not reader.is_chibi(pid):
        raise ValueError("本批叙事插图仅适用于完整赤壁样例。")
    prepared = []
    existing = reader.state_assets(pid)
    # Validate every source before adding any candidate or writing project files.
    for spec in catalog():
        path = ROOT / spec["file"]
        if not path.is_file():
            raise ValueError(f"叙事图尚未准备好：{spec['title']}。")
        raw = path.read_bytes()
        with Image.open(path) as image:
            if image.format != "PNG" or image.width > 4096 or image.height > 4096:
                raise ValueError("叙事插图格式或尺寸无效。")
            size = image.size
            image.verify()
        digest = sha256(raw)
        key = "narrative:" + spec["key"]
        old = next(
            (
                a
                for a in existing
                if a.get("sample_key") == key
                and a["sha256"] == digest
                and a["status"] != "rejected"
            ),
            None,
        )
        if old:
            continue
        prepared.append(
            (
                raw,
                {
                    "id": str(uuid.uuid4()),
                    "kind": "scene",
                    "status": "pending",
                    "sha256": digest,
                    "width": size[0],
                    "height": size[1],
                    "sample_key": key,
                    "origin": "codex_imagegen",
                    "label": spec["title"],
                    "license": "Codex 内置生图；文学艺术化情境。提示词与来源：samples/reader/narrative-v1；最终艺术审查未确认。",
                },
            )
        )
    created = []
    try:
        directory = reader.store.project_dir(pid) / "reader-assets"
        directory.mkdir(exist_ok=True)
        for raw, asset in prepared:
            target = directory / (asset["id"] + ".png")
            target.write_bytes(raw)
            target.chmod(0o444)
            created.append(target)

        def update(db, _config):
            for _, asset in prepared:
                reader.review.put(db, "reader_assets", pid, asset)

        reader.mutate(pid, revision, "reader.narrative.import", update)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return reader.state(pid)


def narrative_chibi(reader, pid, original):
    config = expanded_chibi(reader, pid, copy.deepcopy(original), second_batch=True)
    blocks = reader.blocks(pid)
    assets = {a.get("sample_key"): a for a in reader.state_assets(pid) if a["status"] != "rejected"}
    baseline = list(config["presentations"])
    cues = {p["start_byte"]: p for p in baseline}
    plates = []
    raw = reader.review.source(pid)
    for spec in catalog():
        matches = [b for b in blocks if spec["marker"] in b["text"]]
        if len(matches) != 1:
            raise ValueError(f"叙事图无法唯一定位原文：{spec['title']}。")
        block = matches[0]
        asset = assets.get("narrative:" + spec["key"])
        if not asset:
            raise ValueError(f"请先导入叙事图：{spec['title']}。")
        reader.path(pid, asset["id"])
        plates.append(
            {
                "id": spec["key"],
                "after_byte": block["byte_end"],
                "image_asset_id": asset["id"],
                "title": spec["title"],
                "description": f"{spec['title']} · 文学情境插图",
            }
        )
        # Companion mode uses the whole painting; no standing sprites over a group scene.
        start = block["byte_start"] + len(block["text"].split(spec["marker"])[0].encode())
        if spec["key"] == "river-overlook":
            start = blocks[0]["byte_start"]
        current = next(p for p in reversed(baseline) if p["start_byte"] <= start)
        scene = next(s for s in reversed(config["scenes"]) if s["start_byte"] <= start)
        cues[start] = {
            **current,
            "id": "painting-" + spec["key"],
            "scene_id": scene["id"],
            "start_byte": start,
            "kind": "event",
            "cast": [],
            "image_asset_id": asset["id"],
            "place_label": spec["title"],
        }
        following = next((b for b in blocks if b["byte_start"] > block["byte_end"]), None)
        if following and following["byte_start"] not in cues:
            at = following["byte_start"]
            previous = next(p for p in reversed(baseline) if p["start_byte"] <= at)
            scene = next(s for s in reversed(config["scenes"]) if s["start_byte"] <= at)
            cues[at] = {
                **previous,
                "id": "painting-return-" + spec["key"],
                "scene_id": scene["id"],
                "start_byte": at,
            }
    config.update(
        reading_layout="illustrated",
        illustrations=sorted(plates, key=lambda p: p["after_byte"]),
        presentations=sorted(cues.values(), key=lambda p: p["start_byte"]),
    )
    assert reader.review.source(pid) == raw
    return config
