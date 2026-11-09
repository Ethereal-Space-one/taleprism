"""Local, identity-scoped portrait candidates; never calls an image service."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "samples/characters"
SAMPLES = {
    "kongming": {
        "label": "孔明 · 道衣基础",
        "aliases": ["孔明", "諸葛亮", "诸葛亮"],
        "file": "kongming-v1.png",
        "state": "base",
        "kind": "reference_and_figure",
        "date": "2026-11-03",
    },
    "zhouyu": {
        "label": "周瑜 · 绛衣基础",
        "aliases": ["周瑜", "瑜", "公瑾"],
        "file": "zhouyu-v1.png",
        "state": "base",
        "kind": "reference_and_figure",
        "date": "2026-11-03",
    },
    "caocao": {
        "label": "曹操 · 基础立绘",
        "aliases": ["曹操", "操", "曹孟德", "孟德"],
        "file": "expansion-v1/caocao-base-v1.png",
        "state": "base",
        "kind": "reference_and_figure",
        "date": "2026-11-04",
    },
    "guanyu": {
        "label": "关羽 · 基础立绘",
        "aliases": ["关羽", "關羽", "關雲長", "关云长", "雲長", "云长", "關某"],
        "file": "expansion-v1/guanyu-base-v1.png",
        "state": "base",
        "kind": "reference_and_figure",
        "date": "2026-11-04",
    },
    "lusu": {
        "label": "鲁肃 · 基础立绘",
        "aliases": ["鲁肃", "魯肅", "肅", "子敬", "魯子敬"],
        "file": "expansion-v1/lusu-base-v1.png",
        "state": "base",
        "kind": "reference_and_figure",
        "date": "2026-11-04",
    },
    "huanggai": {
        "label": "黄盖 · 基础立绘",
        "aliases": ["黄盖", "黃蓋", "公覆", "黃公覆", "蓋"],
        "file": "expansion-v1/huanggai-base-v1.png",
        "state": "base",
        "kind": "reference_and_figure",
        "date": "2026-11-04",
    },
    "zhouyu_ill": {
        "label": "周瑜 · 病中半卧",
        "aliases": ["周瑜", "瑜", "公瑾"],
        "file": "expansion-v1/zhouyu-ill-v1.png",
        "state": "ill-seated",
        "kind": "figure",
        "date": "2026-11-04",
    },
    "zhaoyun": {
        "label": "赵云 · 基础立绘",
        "aliases": ["赵云", "趙雲", "趙子龍", "赵子龙", "子龍", "子龙", "雲"],
        "file": "expansion-v2/zhaoyun-base-v1.png",
        "state": "base",
        "kind": "reference_and_figure",
        "date": "2026-11-04",
    },
    "zhangfei": {
        "label": "张飞 · 基础立绘",
        "aliases": ["张飞", "張飛", "張翼德", "张翼德", "翼德", "燕人張翼德"],
        "file": "expansion-v2/zhangfei-base-v1.png",
        "state": "base",
        "kind": "reference_and_figure",
        "date": "2026-11-04",
    },
}


def matches(character, spec):
    return bool({character["display_name"], *character["aliases"]} & set(spec["aliases"]))


def candidates(character):
    if character["status"] in {"merged", "rejected"}:
        return []
    return [
        {"key": key, "label": value["label"], "state": value["state"], "kind": value["kind"]}
        for key, value in SAMPLES.items()
        if matches(character, value) and (ROOT / value["file"]).is_file()
    ]


def import_candidate(review, pid, cid, revision, key):
    spec = SAMPLES.get(key)
    if not spec:
        raise ValueError("此角色候选图不存在。")
    character = next((c for c in review.state(pid)["characters"] if c["id"] == cid), None)
    if not character:
        raise KeyError()
    if not matches(character, spec):
        raise ValueError("候选图与当前人物身份不匹配，请先核对角色与别名。")
    path = ROOT / spec["file"]
    if not path.is_file():
        raise ValueError("此候选图尚未准备好。")
    return review.upload_asset(
        pid,
        revision,
        cid,
        path.read_bytes(),
        spec["kind"],
        f"Codex 内置 image_gen 于 {spec['date']} 生成；{spec['label']}；文学角色艺术化设计，本地工程候选，最终艺术审查未确认。提示词与来源随成品保存。",
        origin="codex_imagegen",
        label=spec["label"],
        sample_key=key,
        portrait_state=spec["state"],
    )
