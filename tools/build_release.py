"""Build and verify local trial assets from source. No upload or paid-model calls."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from build_content_pack import build

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".release/v0.1.0")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    prefix = "taleprism-v" + VERSION
    from export_prompt_kit import outputs

    for name, value in outputs().items():
        if (ROOT / name).read_text() != value:
            raise ValueError("Stale generated prompt/schema: " + name)
    with tempfile.TemporaryDirectory(prefix="taleprism-release-") as temp:
        os.environ["STORYGAL_DATA_DIR"] = str(Path(temp) / "initial")
        from fastapi.testclient import TestClient
        from storygal.app import create_app

        app = create_app(Path(temp) / "build")
        report = build(
            ROOT / "samples/last-light/recipe.json",
            "http://testserver",
            out / (prefix + "-last-light-project.zip"),
            client_factory=lambda **_kw: TestClient(app),
        )
        reader_raw = (
            TestClient(app).get(report["export"]["result"]["download_url"]).content
        )
        reader_zip = out / (prefix + "-last-light-reader.zip")
        reader_zip.write_bytes(reader_raw)
        # The public project is rebuilt from the unchanged, inspected recipe without voice.
        raw = (out / (prefix + "-last-light-project.zip")).read_bytes()
        with zipfile.ZipFile(out / (prefix + "-last-light-project.zip")) as z:
            project = json.loads(z.read("project.json"))
            assert not project["records"]["speech_takes"]
            assert not any(n.startswith("audio/") for n in z.namelist())
        other = TestClient(create_app(Path(temp) / "import"))
        r = other.post("/api/project-bundles", files={"file": ("project.zip", raw)})
        if r.status_code != 201:
            raise ValueError("Public sample import failed: " + r.text)
        pid = r.json()["id"]
        plan = other.get(f"/api/projects/{pid}/production").json()["plan"]
        assert len(plan["shots"]) == 3 and len(plan["scenes"][0]["objects"]) == 11
        assert all(
            s["continuity_check"]["reviewer"] == "assistant" for s in plan["shots"]
        )
        assert (
            other.get(f"/api/projects/{pid}/source").content
            == (ROOT / "samples/last-light/source.txt").read_bytes()
        )
        assert other.get(f"/api/projects/{pid}/delivery").json()["records"] == []
        assert other.post(f"/api/projects/{pid}/reader/exports").status_code == 202
        assert other.get(f"/api/projects/{pid}/jobs").json()[0]["state"] == "completed"
        # Verify every file in the independent reader before making a Pages directory.
        with zipfile.ZipFile(reader_zip) as z:
            manifest = json.loads(z.read("storygal-delivery.json"))
            assert set(z.namelist()) == set(manifest["files"]) | {
                "storygal-delivery.json"
            }
            for name, record in manifest["files"].items():
                content = z.read(name)
                assert (
                    len(content) == record["bytes"]
                    and digest(content) == record["sha256"]
                )
            reader = json.loads(z.read("reader.json"))
            assert not any(a["type"] == "audio" for a in reader["media"].values())
            assert len(reader["config"]["illustrations"]) == 3
            assert all(
                a["url"].startswith("./media/") for a in reader["media"].values()
            )
            site = out / "site"
            if site.exists():
                shutil.rmtree(site)
            z.extractall(site)
        # The private build report contains temporary paths/project IDs; do not publish it.
        (out / (prefix + "-last-light-project.build.json")).unlink()

    starter = out / (prefix + "-prompt-starter.zip")
    files = [
        ROOT / n
        for n in [
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "README.en.md",
            "CONTRIBUTING.md",
            "CHANGELOG.md",
        ]
    ]
    for tree in ["prompts", "schemas", "examples", "samples/last-light"]:
        files.extend(
            p for p in (ROOT / tree).rglob("*") if p.is_file() and p.name != ".DS_Store"
        )
    files.extend(
        ROOT / "docs" / name
        for name in [
            "快速上手.md",
            "COMPATIBILITY.md",
            "使用与恢复指南.md",
            "VALIDATION-v0.1.0.md",
            "ARCHITECTURE.md",
            "人物视觉导演标准.md",
            "RELEASING.md",
        ]
    )
    with zipfile.ZipFile(starter, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(files)):
            z.writestr("taleprism/" + p.relative_to(ROOT).as_posix(), p.read_bytes())
        z.writestr(
            "taleprism/README.md",
            "# Taleprism 0.1.0 prompt starter\n\nStart with [八模板 / Templates](prompts/README.md), [中文教程](examples/last-light/README.md) or [English tutorial](examples/last-light/README.en.md). Images are in samples/last-light. No application installation is needed. To install the workbench, download the source from https://github.com/Ethereal-Space-one/taleprism.\n\nThis archive contains no workbench executable, API credentials or system voice audio. Template examples are not approval of your outputs. Preserve LICENSE and provenance.\n",
        )
    artifacts = []
    for p in [starter, out / (prefix + "-last-light-project.zip"), reader_zip]:
        artifacts.append(
            {
                "file": p.name,
                "bytes": p.stat().st_size,
                "sha256": digest(p.read_bytes()),
            }
        )
    manifest = {
        "product": "Taleprism",
        "version": VERSION,
        "commit": None,
        "artifacts": artifacts,
        "checks": {
            "source_preserved": True,
            "project_import_and_reexport": True,
            "scene_objects": 11,
            "shots": 3,
            "system_audio_included": False,
            "creator_final_review": "pending",
            "external_user_test": "not_yet_validated",
        },
    }
    (out / "release-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    (out / "SHA256SUMS").write_text(
        "".join(a["sha256"] + "  " + a["file"] + "\n" for a in artifacts)
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
