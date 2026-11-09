"""Versioned, source-anchored presentation states; no mutations of the source text."""

import copy


def normalize(config):
    return {
        **copy.deepcopy(config),
        "presentations": config.get("presentations", []),
        "map_entries": config.get("map_entries", []),
        "reading_layout": config.get("reading_layout", "split"),
        "illustrations": config.get("illustrations", []),
    }


def validate(reader, pid, config):
    raw = reader.review.source(pid)
    blocks = reader.blocks(pid)

    def anchor(value):
        if not any(b["byte_start"] <= value < b["byte_end"] for b in blocks):
            raise ValueError("编排锚点必须位于可见原文内。")
        try:
            raw[:value].decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("编排锚点必须位于完整 UTF-8 字符边界。") from None

    review = reader.review.state(pid)
    chars = {c["id"]: c for c in review["characters"] if c["status"] == "confirmed"}
    figures = {a["id"]: a for a in review["assets"] if a["kind"] != "reference"}
    assets = {a["id"]: a for a in reader.state_assets(pid)}
    plates = config.get("illustrations", [])
    ends = {b["byte_end"] for b in blocks}
    if config.get("reading_layout", "split") not in {"split", "illustrated"}:
        raise ValueError("未知阅读布局。")
    if (
        len(plates) > 64
        or len({p["id"] for p in plates}) != len(plates)
        or [p["after_byte"] for p in plates] != sorted({p["after_byte"] for p in plates})
    ):
        raise ValueError("章节插图须按唯一原文位置排序，最多 64 张。")
    for p in plates:
        if p["after_byte"] not in ends:
            raise ValueError("章节插图须放在完整原文段落之后。")
        if assets.get(p["image_asset_id"], {}).get("kind") != "scene":
            raise ValueError("章节插图必须属于本项目的场景素材。")
        if not p["title"].strip() or len(p["title"]) > 80 or len(p.get("description", "")) > 300:
            raise ValueError("请填写简短的插图名称与说明。")
    scenes = config["scenes"]
    presentations = config.get("presentations", [])
    starts = [p["start_byte"] for p in presentations]
    if starts != sorted(set(starts)) or len({p["id"] for p in presentations}) != len(presentations):
        raise ValueError("呈现记录必须按唯一原文位置排序，编号不可重复。")
    if presentations and {s["start_byte"] for s in scenes} - set(starts):
        raise ValueError("每个大场景起始处必须有完整呈现记录。")
    for p in presentations:
        anchor(p["start_byte"])
        scene = next((s for s in reversed(scenes) if s["start_byte"] <= p["start_byte"]), None)
        if not scene or scene["id"] != p["scene_id"]:
            raise ValueError("呈现记录不在指定场景内。")
        if p["image_asset_id"] not in assets or assets[p["image_asset_id"]]["kind"] != "scene":
            raise ValueError("呈现图片必须属于本项目的场景素材。")
        cast = p["cast"]
        if len({c["slot"] for c in cast}) != len(cast) or len(
            {c["character_id"] for c in cast}
        ) != len(cast):
            raise ValueError("人物与左右位置不能重复。")
        if p["kind"] == "event" and cast:
            raise ValueError("事件插画不叠加人物，请配置后续呈现恢复人物。")
        for member in cast:
            char, figure = chars.get(member["character_id"]), figures.get(member["figure_asset_id"])
            if not char or not figure or figure["character_id"] != member["character_id"]:
                raise ValueError("呈现人物需确认，立绘必须属于对应角色。")
            if figure["status"] == "rejected":
                raise ValueError("呈现使用了已拒绝的立绘。")
    if presentations and presentations[-1]["kind"] == "event":
        raise ValueError("事件画面后需要配置恢复呈现。")
    entries = config.get("map_entries", [])
    if len({e["id"] for e in entries}) != len(entries):
        raise ValueError("地图入口编号不可重复。")
    if entries and config.get("map_profile") != "chibi":
        raise ValueError("地图入口需要启用适用的地图。")
    import json

    from .reader import REPO

    data = json.loads((REPO / "samples/reader/chibi-map.json").read_text())
    places = {p["id"] for p in data["places"]}
    for e in entries:
        anchor(e["byte_start"])
        if e["byte_end"] <= e["byte_start"] or e["byte_end"] > len(raw):
            raise ValueError("地图入口原文范围无效。")
        try:
            raw[e["byte_start"] : e["byte_end"]].decode()
        except UnicodeDecodeError:
            raise ValueError("地图入口范围须为完整字符。") from None
        if (
            e["phase_id"] not in {"opposition", "fire", "retreat"}
            or not set(e["place_ids"]) <= places
        ):
            raise ValueError("地图入口的阶段或地点不存在。")


def legacy_presentations(config, characters):
    return [
        {
            "id": "legacy-" + s["id"],
            "scene_id": s["id"],
            "start_byte": s["start_byte"],
            "kind": "dialogue" if s["character_ids"] else "environment",
            "image_asset_id": s["asset_id"],
            "place_label": s["title"],
            "time_label": "",
            "cast": [
                {"character_id": cid, "figure_asset_id": characters[cid]["figure_id"], "slot": slot}
                for cid, slot in zip(s["character_ids"][:2], ["left", "right"])
                if cid in characters and characters[cid]["figure_id"]
            ],
        }
        for s in config["scenes"]
    ]


def chibi(reader, pid, config):
    if not reader.is_chibi(pid):
        raise ValueError("此编排仅适用于完整赤壁样例。")
    raw = reader.review.source(pid)
    characters = {
        c["display_name"]: c
        for c in reader.review.state(pid)["characters"]
        if c["status"] == "confirmed"
    }

    def position(quote):
        return raw.index(quote.encode())

    def cast(names):
        return [
            {
                "character_id": characters[n]["id"],
                "figure_asset_id": characters[n]["active_figure_id"],
                "slot": slot,
            }
            for n, slot in zip(names, ["left", "right"])
            if n in characters and characters[n]["active_figure_id"]
        ]

    result = []
    for s in config["scenes"]:
        result.append(
            {
                "id": "scene-" + s["id"],
                "start_byte": s["start_byte"],
                "scene_id": s["id"],
                "kind": "environment",
                "image_asset_id": s["asset_id"],
                "place_label": s["title"],
                "time_label": "",
                "cast": [],
            }
        )
    fire_scene = next((s for s in config["scenes"] if s["title"] == "火起江面"), None)
    if fire_scene:
        first = next(p for p in result if p["scene_id"] == fire_scene["id"])
        previous = next(
            (s for s in reversed(config["scenes"]) if s["start_byte"] < fire_scene["start_byte"]),
            None,
        )
        if previous:
            first["image_asset_id"] = previous["asset_id"]
        result.append(
            {
                **first,
                "id": "fire-begins",
                "kind": "event",
                "start_byte": position("黃蓋用刀一招"),
                "image_asset_id": fire_scene["asset_id"],
            }
        )
    # A standing portrait is intentionally not used while Zhou Yu is ill or seated.
    for quote, names in [("瑜命請入", ["孔明"]), ("瑜聞言大喜，矍然而起", ["孔明", "周瑜"])]:
        at = position(quote)
        scene = next(s for s in reversed(config["scenes"]) if s["start_byte"] <= at)
        result.append(
            {
                "id": "entrance-" + str(at),
                "start_byte": at,
                "scene_id": scene["id"],
                "kind": "dialogue",
                "image_asset_id": scene["asset_id"],
                "place_label": scene["title"],
                "time_label": "",
                "cast": cast(names),
            }
        )
    config["presentations"] = sorted(result, key=lambda p: p["start_byte"])
    config["map_entries"] = [
        {
            "id": "chibi-" + phase,
            "byte_start": position(quote),
            "byte_end": position(quote) + len(quote.encode()),
            "label": label,
            "phase_id": phase,
            "place_ids": places,
        }
        for phase, quote, label, places in [
            ("opposition", "是日看看近夜", "查看此时两军的位置", ["chibi", "wulin"]),
            ("fire", "黃蓋用刀一招", "查看火攻方向", ["chibi", "wulin"]),
            ("retreat", "縱馬加鞭", "查看约略撤军方向", ["jiangling"]),
        ]
    ]
    return config
