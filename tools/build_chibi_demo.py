"""Export the reviewed Chibi showcase from an isolated copy, leaving local projects intact."""

import argparse
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build(source, output):
    raw = source.read_bytes()
    review = json.loads((ROOT / "examples/chibi/demo-review.json").read_text())
    if digest(raw) != review["source_bundle_sha256"]:
        raise ValueError(
            "Chibi source bundle changed; inspect it before rebuilding the public demo."
        )
    with tempfile.TemporaryDirectory(prefix="taleprism-chibi-") as temp:
        os.environ["STORYGAL_DATA_DIR"] = str(Path(temp) / "initial")
        from fastapi.testclient import TestClient
        from storygal.app import create_app

        app = create_app(Path(temp) / "demo")
        client = TestClient(app)
        response = client.post(
            "/api/project-bundles", files={"file": ("chibi.zip", raw)}
        )
        response.raise_for_status()
        pid = response.json()["id"]
        reader, speech = app.state.reader, app.state.speech
        assets = reader.state_assets(pid)
        pending = {a["sample_key"]: a for a in assets if a["status"] == "pending"}
        if set(pending) != {item["sample_key"] for item in review["images"]}:
            raise ValueError("Pending images do not match the recorded inspection.")
        for item in review["images"]:
            asset = pending[item["sample_key"]]
            if asset["sha256"] != item["sha256"]:
                raise ValueError("Inspected image changed: " + item["sample_key"])
            reader.accept(pid, reader.load(pid)[0], asset["id"], "accepted")
        # Keep existing local voice assets private; no synthesis or network request occurs.
        for did, line in speech.load(pid)[1]["lines"].items():
            speech.line(pid, speech.load(pid)[0], did, False, line.get("overrides", {}))
        assert not app.state.delivery.state(pid)["records"]
        response = client.post(f"/api/projects/{pid}/reader/exports")
        response.raise_for_status()
        job = next(
            j for j in app.state.store.jobs(pid) if j["id"] == response.json()["job_id"]
        )
        if job["state"] != "completed":
            raise ValueError(job.get("error", "Reader export incomplete"))
        exported = client.get(job["result"]["download_url"])
        exported.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
            files = {name: z.read(name) for name in z.namelist()}
        content = json.loads(files["reader.json"])
        assert content["config"]["title"] == "赤壁"
        assert len(content["config"]["illustrations"]) == 12
        assert len(content["presentations"]) == 55
        assert len(content["characters"]) == 8
        assert len(content["map"]["phases"]) == 3
        assert sum(a["type"] == "figure" for a in content["media"].values()) == 9
        assert not any(a["type"] == "audio" for a in content["media"].values())
        original = (
            ROOT / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt"
        ).read_bytes()
        assert files["storygal-source/original.txt"] == original
        assert digest(source.read_bytes()) == review["source_bundle_sha256"]

    files["storygal-source/chibi-demo-review.json"] = json.dumps(
        review, ensure_ascii=False, indent=2
    ).encode()
    files["storygal-source/novel/PROVENANCE.md"] = (
        ROOT / "samples/sanguo-chibi/PROVENANCE.md"
    ).read_bytes()
    files["storygal-source/tools/wikisource_to_txt.py"] = (
        ROOT / "samples/tools/wikisource_to_txt.py"
    ).read_bytes()
    files["licenses/Taleprism-MIT.txt"] = (ROOT / "LICENSE").read_bytes()
    files["SHOWCASE.txt"] = (
        "Taleprism 赤壁在线主示例：12幅情境图、8位主要角色、9张立绘、3阶段阅读地图。\n"
        "两张心理表演修订图已完成助手制作检查；仅在公开示例副本接受，不更改原工程。"
        "用户最终美术复核仍未代填。公开版本不含本机系统演示音频。\n"
        "正文来源及版本见 storygal-source/novel/PROVENANCE.md；"
        "图片检查见 storygal-source/chibi-demo-review.json；地图为约略阅读辅助。\n"
    ).encode()
    inventory = json.loads(files.pop("storygal-delivery.json"))
    inventory["files"] = {
        name: {"bytes": len(value), "sha256": digest(value)}
        for name, value in sorted(files.items())
    }
    files["storygal-delivery.json"] = json.dumps(
        inventory, ensure_ascii=False, indent=2
    ).encode()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "taleprism-v0.1.0-chibi-reader.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for name, value in files.items():
            z.writestr(name, value)
    record = {
        "file": archive.name,
        "bytes": archive.stat().st_size,
        "sha256": digest(archive.read_bytes()),
        "source_bundle_sha256": review["source_bundle_sha256"],
        "source_sha256": digest(original),
        "illustrations": 12,
        "characters": 8,
        "portraits": 9,
        "presentations": 55,
        "map_phases": 3,
        "system_audio_included": False,
        "production_reviewer": "assistant",
        "creator_final_art_review": "pending",
    }
    (output / "chibi-demo-manifest.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "samples/content-packs/chibi.storygal.zip"
    )
    parser.add_argument("--output", type=Path, default=ROOT / ".release/chibi-demo")
    args = parser.parse_args()
    build(args.source, args.output)
