"""Prepare an isolated, reproducible reader sample through the local application API."""

import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def prepare(base, filename="P5-赤壁视觉阅读.txt"):
    with httpx.Client(base_url=base, timeout=120) as client:

        def call(path, method="GET", body=None):
            response = client.request(method, path, json=body)
            response.raise_for_status()
            return response.json()

        raw = (ROOT / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt").read_bytes()
        response = client.post(
            "/api/projects",
            files={"file": (filename, raw, "text/plain")},
            data={"rights_status": "public_domain"},
        )
        response.raise_for_status()
        project = response.json()
        prefix = "/api/projects/" + project["id"]

        def review():
            return call(prefix + "/review")

        def speech():
            return call(prefix + "/speech")

        state = review()
        target = next(c for c in state["characters"] if c["display_name"] == "周瑜")
        alias = next(
            (c for c in state["characters"] if c["display_name"] == "瑜"), None
        )
        if alias:
            call(
                prefix + f"/characters/{alias['id']}/merge",
                "POST",
                {"revision": state["revision"], "target_id": target["id"]},
            )
        voices = speech()["capabilities"]["voices"]
        for name, sample, voice_prefix in [
            ("孔明", "kongming", "Eddy"),
            ("周瑜", "zhouyu", "Tingting"),
        ]:
            state = review()
            character = next(
                c for c in state["characters"] if c["display_name"] == name
            )
            call(
                prefix + f"/characters/{character['id']}",
                "PATCH",
                {
                    "revision": state["revision"],
                    "display_name": name,
                    "aliases": character["aliases"],
                    "status": "confirmed",
                },
            )
            state = review()
            asset = call(
                prefix + f"/characters/{character['id']}/codex-sample",
                "POST",
                {"revision": state["revision"], "sample_key": sample},
            )
            call(
                prefix + f"/assets/{asset['id']}",
                "PATCH",
                {
                    "revision": review()["revision"],
                    "status": "accepted",
                    "active": True,
                },
            )
            state = review()
            dialogue = next(
                d
                for d in state["dialogues"]
                if (
                    d["text"].startswith("亮雖不才，曾遇異人")
                    if name == "孔明"
                    else d["text"] == "心腹攪痛，時復昏迷。"
                )
            )
            call(
                prefix + "/dialogues",
                "PATCH",
                {
                    "revision": state["revision"],
                    "dialogue_ids": [dialogue["id"]],
                    "speaker_id": character["id"],
                },
            )
            voice = next(v for v in voices if v.startswith(voice_prefix))
            call(
                prefix + f"/speech/profiles/{character['id']}",
                "PATCH",
                {"revision": speech()["revision"], "voice": voice, "speed": 180},
            )
            call(
                prefix + f"/speech/lines/{dialogue['id']}",
                "PATCH",
                {"revision": speech()["revision"], "selected": True},
            )
            job = call(
                prefix + "/speech/generate", "POST", {"dialogue_id": dialogue["id"]}
            )
            for _ in range(300):
                result = next(
                    j for j in call(prefix + "/jobs") if j["id"] == job["job_id"]
                )
                if result["state"] != "running":
                    break
                time.sleep(0.2)
            if result["state"] != "completed":
                raise RuntimeError(result.get("error") or "语音任务未完成")
            audio = speech()
            line = next(l for l in audio["lines"] if l["id"] == dialogue["id"])
            call(
                prefix + f"/speech/lines/{dialogue['id']}/accept",
                "POST",
                {
                    "revision": audio["revision"],
                    "take_ids": {
                        s["key"]: s["candidate"]["id"] for s in line["segments"]
                    },
                },
            )
        # Candidate cover/backgrounds remain pending for UI review and export-gate verification.
        reader = call(prefix + "/reader")
        call(prefix + "/reader/sample", "POST", {"revision": reader["revision"]})
        return {
            "project_id": project["id"],
            "reader_url": f"/read/{project['id']}",
            "original_bytes": len(raw),
            "manual_review": "pending",
            "pending_dialogues": review()["pending_count"],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    result = prepare(args.base)
    output = ROOT / "data/verification/p5"
    output.mkdir(parents=True, exist_ok=True)
    (output / "fixture.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    print(json.dumps(result, ensure_ascii=False))
