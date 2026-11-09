"""Create an isolated P6 review chapter with real local voices; never alter P5 fixtures."""

import argparse
import json
from pathlib import Path

import httpx
from prepare_reader_sample import prepare

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    result = prepare(args.base, filename="P6-赤壁重温阅读.txt")
    with httpx.Client(base_url=args.base, timeout=120) as client:
        prefix = "/api/projects/" + result["project_id"] + "/reader"
        state = client.get(prefix).json()
        for asset in state["assets"]:
            latest = client.get(prefix).json()
            r = client.patch(
                prefix + "/assets/" + asset["id"],
                json={"revision": latest["revision"], "status": "accepted"},
            )
            r.raise_for_status()
        latest = client.get(prefix).json()
        r = client.post(
            prefix + "/choreography/sample", json={"revision": latest["revision"]}
        )
        r.raise_for_status()
    out = Path(__file__).resolve().parents[1] / "data/verification/p6"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixture.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))
