"""Prepare an isolated illustrated edition from local reviewed-for-demo media only."""

import argparse
import json
from pathlib import Path

import httpx
from prepare_p7_sample import expand
from prepare_p8_sample import ROLES
from prepare_reader_sample import prepare

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    fixture = prepare(args.base, filename="P9-赤壁章节画卷.txt")
    with httpx.Client(base_url=args.base, timeout=120) as client:
        pid = fixture["project_id"]
        expand(client, pid, extra_roles=ROLES)
        prefix = f"/api/projects/{pid}/reader"

        def state():
            result = client.get(prefix)
            result.raise_for_status()
            return result.json()

        def post(path):
            result = client.post(prefix + path, json={"revision": state()["revision"]})
            result.raise_for_status()

        post("/narrative/sample")
        for asset in state()["assets"]:
            if asset["status"] != "accepted":
                result = client.patch(
                    prefix + "/assets/" + asset["id"],
                    json={"revision": state()["revision"], "status": "accepted"},
                )
                result.raise_for_status()
        post("/choreography/narrative-sample")
        content = client.get(prefix + "/content").json()
    fixture.update(
        characters=len(content["characters"]),
        figures=sum(a["type"] == "figure" for a in content["media"].values()),
        illustrations=len(content["config"]["illustrations"]),
        presentations=len(content["presentations"]),
        art_review="pending",
        voices="unchanged: two selected lines / three real local clips",
        layout="illustrated",
    )
    out = Path(__file__).resolve().parents[1] / "data/verification/p9"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2))
    print(json.dumps(fixture, ensure_ascii=False))
