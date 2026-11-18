"""Build a real independent reader via the normal creator API; generated QA material only."""

import io
import json
import math
import os
import struct
import sys
import tempfile
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image


def main(out):
    with tempfile.TemporaryDirectory() as temp:
        from fastapi.testclient import TestClient

        os.environ["STORYGAL_DATA_DIR"] = str(Path(temp) / "initial")
        from storygal import speech
        from storygal.app import create_app
        from storygal.text import sha256

        c = TestClient(create_app(Path(temp) / "creator"))
        raw = "第一章 門燈\n雨点落进院里的水洼。\n甲曰：「等一会儿。」\n标牌刻有 </ScRiPt> & <字>。".encode()
        pid = c.post(
            "/api/projects",
            files={"file": ("离线短章.txt", raw)},
            data={"rights_status": "owned"},
        ).json()["id"]
        reader = c.app.state.reader
        # Incompressible enough to expose accidental base64 expansion/inline duplication.
        png = io.BytesIO()
        Image.effect_noise((1800, 1200), 90).save(png, format="PNG")
        asset = reader.upload(
            pid, 0, png.getvalue(), "scene", "Generated offline QA image"
        )
        reader.accept(pid, reader.load(pid)[0], asset["id"], "accepted")
        rev, config = reader.load(pid)
        anchor = reader.blocks(pid)[1]["byte_end"]
        area = [[[0.1, 0.3], [0.8, 0.3], [0.8, 0.9], [0.1, 0.9]]]
        config.update(
            title="离线短章",
            reading_layout="illustrated",
            illustrations=[
                {
                    "id": "qa-rain",
                    "after_byte": anchor,
                    "image_asset_id": asset["id"],
                    "title": "水洼",
                    "description": "合成颗粒测试图，仅验证本地加载。",
                    "motion": {
                        "version": 1,
                        "effect": "rain-wet-ground",
                        "image_sha256": asset["sha256"],
                        "source_sha256": sha256(raw),
                        "after_byte": anchor,
                        "width": 1800,
                        "height": 1200,
                        "evidence": "雨点落进院里的水洼",
                        "note": "合成测试检查此处的可见区域。",
                        "reviewed": True,
                        "areas": area,
                        "ground": area,
                        "drops": 36,
                        "rings": 8,
                    },
                }
            ],
        )
        reader.save(pid, rev, config)
        review = c.app.state.review
        char = review.state(pid)["characters"][0]
        review.character(
            pid, review.state(pid)["revision"], char["display_name"], [], "", char["id"]
        )
        did = review.state(pid)["dialogues"][0]["id"]
        review.assign(pid, review.state(pid)["revision"], [did], char["id"])

        # Only the synthesis engine is replaced. The normal store, acceptance,
        # checksums, WAV validation, snapshot job and download are exercised.
        def make_wav(_text, _voice, _speed, path):
            with wave.open(str(path), "wb") as w:
                w.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                w.writeframes(
                    b"".join(
                        struct.pack(
                            "<h", int(1600 * math.sin(2 * math.pi * 220 * i / 24000))
                        )
                        for i in range(48000)
                    )
                )

        caps = {
            "provider": "macos-say",
            "model": "fixture",
            "version": 1,
            "format": "pcm",
            "voices": ["generated"],
            "available": True,
        }
        with (
            patch.object(speech, "render", make_wav),
            patch.object(speech, "voices", return_value=["generated"]),
            patch.object(speech, "capabilities", return_value=caps),
        ):
            s = c.app.state.speech
            s.profile(pid, s.state(pid)["revision"], char["id"], "generated", 180)
            s.line(pid, s.state(pid)["revision"], did, True, {})
            s.synthesize(pid, did)
            segs = s.state(pid)["lines"][0]["segments"]
            s.accept(
                pid,
                s.state(pid)["revision"],
                did,
                {x["key"]: x["candidate"]["id"] for x in segs},
            )
            # Separate creator-uploaded paragraph cue, not a second speech_take.
            local_wav = Path(temp) / "private-take-name.wav"
            make_wav("", "", 0, local_wav)
            base = f"/api/projects/{pid}/reader/narrations"
            uploaded = c.post(
                base,
                files={"file": (local_wav.name, local_wav.read_bytes())},
                data={
                    "revision": reader.load(pid)[0],
                    "byte_start": reader.blocks(pid)[1]["byte_start"],
                    "credit": "QA_PRIVATE_CREDIT",
                    "publish_credit": "false",
                },
            )
            assert uploaded.status_code == 201, uploaded.text
            state = uploaded.json()
            assert (
                c.patch(
                    base + "/" + state["takes"][0]["id"],
                    json={"revision": state["revision"], "status": "accepted"},
                ).status_code
                == 200
            )
            ambient = f"/api/projects/{pid}/reader/soundscapes"
            block = reader.blocks(pid)[1]
            created = c.post(
                ambient,
                json={
                    "revision": c.get(ambient).json()["revision"],
                    "byte_start": block["byte_start"],
                    "evidence": "雨点落进院里的水洼",
                    "rain": True,
                    "car_at": None,
                },
            )
            assert created.status_code == 201, created.text
            draft = created.json()
            approved = c.patch(
                ambient + "/" + draft["takes"][0]["id"],
                json={"revision": draft["revision"], "status": "accepted"},
            )
            assert approved.status_code == 200, approved.text
            response = c.post(f"/api/projects/{pid}/reader/exports")
            assert response.status_code == 202, response.text
            job = c.get(f"/api/projects/{pid}/jobs").json()[0]
            assert job["state"] == "completed", job
            snapshot = c.get(job["result"]["download_url"]).content
        with zipfile.ZipFile(io.BytesIO(snapshot)) as z:
            assert z.testzip() is None
            z.extractall(out)
            story = json.loads(z.read("reader.json"))
            assert (
                not story["preview"]
                and len(story["media"]) == 4
                and story["schema_version"] == 5
            )
            assert story["blocks"][1]["narration"]["label"] == "段落朗读"
            public_motion = story["config"]["illustrations"][0]["motion"]
            assert public_motion["reviewed"] and public_motion["playback_only"]
            assert not {"note", "evidence"} & public_motion.keys()
            assert all(
                b"QA_PRIVATE_CREDIT" not in z.read(n)
                and b"private-take-name" not in z.read(n)
                and "合成测试检查此处的可见区域。".encode() not in z.read(n)
                for n in z.namelist()
            )
            assert z.read("storygal-source/original.txt") == raw


if __name__ == "__main__":
    main(Path(sys.argv[1]))
