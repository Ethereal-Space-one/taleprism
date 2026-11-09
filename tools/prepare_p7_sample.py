"""Prepare an isolated six-role review chapter using local portraits and system speech."""

import argparse
import json
from pathlib import Path

import httpx
from prepare_reader_sample import prepare

ROLES = {
    "caocao": ("曹操", ["曹操", "操", "孟德", "曹孟德"]),
    "guanyu": ("关羽", ["關雲長", "雲長", "關某", "關羽", "云长", "关云长"]),
    "lusu": ("鲁肃", ["魯肅", "肅", "子敬", "魯子敬"]),
    "huanggai": ("黄盖", ["黃蓋", "蓋", "公覆", "黃公覆"]),
}


def expand(client, pid, extra_roles=None):
    prefix = "/api/projects/" + pid

    def call(path, method="GET", body=None):
        response = client.request(method, prefix + path, json=body)
        response.raise_for_status()
        return response.json()

    for key, (name, aliases) in (ROLES | (extra_roles or {})).items():
        state = call("/review")
        choices = [
            c
            for c in state["characters"]
            if c["status"] not in {"merged", "rejected"}
            and {c["display_name"], *c["aliases"]} & {name, *aliases}
        ]
        if choices:
            target = choices[0]
            for other in choices[1:]:
                call(
                    f"/characters/{other['id']}/merge",
                    "POST",
                    {
                        "revision": call("/review")["revision"],
                        "target_id": target["id"],
                    },
                )
            target = next(
                c for c in call("/review")["characters"] if c["id"] == target["id"]
            )
            call(
                f"/characters/{target['id']}",
                "PATCH",
                {
                    "revision": call("/review")["revision"],
                    "display_name": name,
                    "aliases": sorted(
                        {*target["aliases"], target["display_name"], *aliases} - {name}
                    ),
                    "description": "赤壁角色形象；身份与别名依据本样例人工整理，未确认的对白保持待审。",
                    "status": "confirmed",
                },
            )
        else:
            target = call(
                "/characters",
                "POST",
                {
                    "revision": state["revision"],
                    "display_name": name,
                    "aliases": aliases,
                    "description": "赤壁角色形象，原文别名人工整理。",
                    "status": "confirmed",
                },
            )
        asset = call(
            f"/characters/{target['id']}/codex-sample",
            "POST",
            {"revision": call("/review")["revision"], "sample_key": key},
        )
        call(
            f"/assets/{asset['id']}",
            "PATCH",
            {
                "revision": call("/review")["revision"],
                "status": "accepted",
                "active": True,
            },
        )
    zhou = next(c for c in call("/review")["characters"] if c["display_name"] == "周瑜")
    ill = call(
        f"/characters/{zhou['id']}/codex-sample",
        "POST",
        {"revision": call("/review")["revision"], "sample_key": "zhouyu_ill"},
    )
    call(
        f"/assets/{ill['id']}",
        "PATCH",
        {
            "revision": call("/review")["revision"],
            "status": "accepted",
            "active": False,
        },
    )
    state = call("/reader")
    for asset in state["assets"]:
        if asset["status"] != "accepted":
            call(
                "/reader/assets/" + asset["id"],
                "PATCH",
                {"revision": call("/reader")["revision"], "status": "accepted"},
            )
    call(
        "/reader/choreography/second-sample"
        if extra_roles
        else "/reader/choreography/expanded-sample",
        "POST",
        {"revision": call("/reader")["revision"]},
    )
    return call("/reader/content")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    fixture = prepare(args.base, filename="P7-赤壁六角色首批.txt")
    with httpx.Client(base_url=args.base, timeout=120) as client:
        content = expand(client, fixture["project_id"])
    fixture.update(
        characters=6,
        figures=7,
        presentations=len(content["presentations"]),
        art_review="pending",
        voices="unchanged: two selected lines / three real clips",
    )
    out = Path(__file__).resolve().parents[1] / "data/verification/p7"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2))
    print(json.dumps(fixture, ensure_ascii=False))
