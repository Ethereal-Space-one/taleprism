"""Reviewed excerpt-specific portrait allocation, kept separate from generic reader logic."""

import copy

from .character_samples import SAMPLES
from .reader_presentation import chibi


def expanded_chibi(reader, pid, original, *, second_batch=False):
    config = chibi(reader, pid, copy.deepcopy(original))
    state = reader.review.state(pid)
    raw = reader.review.source(pid)
    characters = {}
    keys = ["kongming", "zhouyu", "caocao", "guanyu", "lusu", "huanggai"]
    if second_batch:
        keys += ["zhaoyun", "zhangfei"]
    for key in keys:
        labels = set(SAMPLES[key]["aliases"])
        matches = [
            c
            for c in state["characters"]
            if c["status"] == "confirmed"
            and labels.intersection([c["display_name"], *c["aliases"]])
        ]
        if len(matches) != 1:
            raise ValueError(
                f"请先确认并合并 {SAMPLES[key]['label'].split(' · ')[0]} 的身份与别名。"
            )
        characters[key] = matches[0]
    figures = {
        a["id"]: a
        for a in state["assets"]
        if a["kind"] != "reference" and a["status"] != "rejected"
    }
    for key, c in characters.items():
        if c["active_figure_id"] not in figures:
            raise ValueError(f"请先为 {SAMPLES[key]['label'].split(' · ')[0]} 设置基础立绘。")
        if figures[c["active_figure_id"]].get("portrait_state", "base") != "base":
            raise ValueError("病中等状态图不应设为通用基础立绘，请先切回基础图。")
    ill = next(
        (
            a
            for a in figures.values()
            if a["character_id"] == characters["zhouyu"]["id"]
            and a.get("sample_key") == "zhouyu_ill"
        ),
        None,
    )
    if not ill:
        raise ValueError("请先导入周瑜病中半卧状态图。")
    images = {a.get("sample_key"): a["id"] for a in reader.state_assets(pid)}
    by_start = {p["start_byte"]: p for p in config["presentations"]}

    def put(quote, names=(), *, illness=False, background=None, place=None):
        needle = quote.encode()
        if raw.count(needle) != 1:
            raise ValueError(f"编排引句无法唯一定位：{quote}")
        at = raw.index(needle)
        scene = next(s for s in reversed(config["scenes"]) if s["start_byte"] <= at)
        current = next(
            p
            for p in sorted(by_start.values(), key=lambda p: p["start_byte"], reverse=True)
            if p["start_byte"] <= at
        )
        # Every cue is a complete state, not a show/hide event that depends on navigation history.
        cast = [
            {
                "character_id": characters[key]["id"],
                "figure_asset_id": ill["id"]
                if illness and key == "zhouyu"
                else characters[key]["active_figure_id"],
                "slot": slot,
            }
            for key, slot in zip(names, ["left", "right"])
        ]
        by_start[at] = {
            "id": "cast-" + str(at),
            "start_byte": at,
            "scene_id": scene["id"],
            "kind": "dialogue" if cast else "environment",
            "image_asset_id": images.get(background, current["image_asset_id"])
            if background
            else current["image_asset_id"],
            "place_label": place or scene["title"],
            "time_label": "",
            "cast": cast,
        }

    put("左右救回帳中", ["zhouyu"], illness=True, background="tent", place="帐中养病")
    put("卻說魯肅見周瑜臥病", ["lusu", "zhouyu"], illness=True, background="tent", place="帐中问疾")
    put("來見孔明，言周瑜猝病之事", ["lusu", "kongming"], background="tent", place="鲁肃请医")
    put("肅先入見周瑜", ["lusu", "zhouyu"], illness=True, background="tent", place="帐中问疾")
    put("瑜命請入", ["kongming", "zhouyu"], illness=True, background="tent", place="孔明问疾")
    put("瑜聞言大喜，矍然而起", ["kongming", "zhouyu"], background="tent", place="商议借风")
    put("來到壇前，分付魯肅曰", ["kongming", "lusu"], background="altar", place="南屏山·祭风")
    put("魯肅別去", ["kongming"], background="altar", place="南屏山·祭风")
    put("孔明緩步登壇", background="altar", place="七星坛")
    put("觀瞻方位已定", ["kongming"], background="altar", place="七星坛")
    put("下壇入帳中少歇", background="altar", place="南屏山")
    put("且說周瑜請程普、魯肅一班軍官", ["zhouyu", "lusu"], background="tent", place="军帐候风")
    put("黃蓋已自準備火船二十隻", ["huanggai"], background="fleet", place="火船待发")
    put("甘寧、闞澤窩盤蔡和、蔡中", background="fleet", place="江东水寨")
    put("瑜即差魯肅遍告各部下官兵將士", ["lusu"], background="tent", place="军令传达")
    put("瑜出帳看時時", ["zhouyu", "lusu"], background="fleet", place="东风起")
    put("二將領命。徐盛下船", background="fleet", place="江上追寻")
    put("孔明便與玄德、劉琦升帳坐定", ["kongming"], background="tent", place="夏口部署")
    put("時雲長在側", ["kongming", "guanyu"], background="tent", place="华容军令")
    put("雲長領了將令", ["kongming"], background="tent", place="夏口部署")
    put("孔明遂與玄德往樊口", background="fleet", place="樊口观战")
    put("卻說曹操在大寨中", ["caocao"], background="fleet", place="曹军水寨")
    put("且說江東，天色向晚", ["zhouyu"], background="tent", place="江东出兵")
    put("黃蓋在第三隻火船上", ["huanggai"], background="fleet", place="黄盖出发")
    put("是時東風大作，波浪洶湧", ["caocao"], background="fleet", place="曹军观船")
    # Fire is already an event in P6. Do not overlay healthy portraits on injury or flight.
    put("曹操回觀岸上營寨", background="fire", place="赤壁火攻")
    put("為首大將關雲長", ["guanyu"], background="forest", place="华容道相逢")
    put("操從其說，即縱馬向前", ["caocao", "guanyu"], background="forest", place="华容道交锋")
    put("於是把馬頭勒回", background="forest", place="义释曹操")
    put("孔明忙離坐席", ["kongming", "guanyu"], background="tent", place="夏口复命")
    put("遂叱武士推出斬之", background="tent", place="军令问责")
    if second_batch:
        # Standing portraits mark recognition and orders; mounted combat remains environmental.
        put("須臾到，孔明、子龍登岸", ["kongming", "zhaoyun"], background="fleet", place="夏口迎归")
        put(
            "孔明便與玄德、劉琦升帳坐定",
            ["kongming", "zhaoyun"],
            background="tent",
            place="子龙领令",
        )
        put("雲領計去了", ["kongming"], background="tent", place="夏口部署")
        put("又喚張飛曰", ["kongming", "zhangfei"], background="tent", place="翼德领令")
        put("飛領計去了", ["kongming"], background="tent", place="夏口部署")
    config["presentations"] = sorted(by_start.values(), key=lambda p: p["start_byte"])
    return config
