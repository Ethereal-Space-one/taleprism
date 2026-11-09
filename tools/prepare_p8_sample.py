"""Isolated eight-role chapter; no cloud speech or new image calls."""

import argparse
import json
from pathlib import Path

import httpx
from prepare_p7_sample import expand
from prepare_reader_sample import prepare

ROLES = {
    "zhaoyun": ("赵云", ["趙雲", "趙子龍", "赵子龙", "子龍", "子龙", "雲"]),
    "zhangfei": ("张飞", ["張飛", "張翼德", "张翼德", "翼德", "燕人張翼德"]),
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    fixture = prepare(args.base, filename="P8-赤壁八角色二期.txt")
    with httpx.Client(base_url=args.base, timeout=120) as client:
        content = expand(client, fixture["project_id"], extra_roles=ROLES)
    fixture.update(
        characters=8,
        figures=9,
        presentations=len(content["presentations"]),
        art_review="pending",
        openai_speech="prepared only; no API key or cloud calls",
        voices="unchanged: two selected lines / three real local clips",
    )
    out = Path(__file__).resolve().parents[1] / "data/verification/p8"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2))
    print(json.dumps(fixture, ensure_ascii=False))
