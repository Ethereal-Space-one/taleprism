"""Rebuild Chibi's editable project and reader from the pinned public v0.1.0 reader.

Offline: --source is a local downloaded ZIP. No private project, user data, voice
synthesis, image generation or network fetch is involved.
"""

import argparse
import copy
import importlib
import io
import json
import os
import re
import tempfile
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from chibi_provenance import GATE, GUIDE, TRACE, provenance_assets
from chibi_source import digest, encoded, preflight, read_zip, verify_inventory
from release_version import PREFIX, VERSION

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "examples/chibi/rebuild-v0.2.0.json"
REVIEW = ROOT / "examples/chibi/visual-review-v0.2.0.json"
# This reviewed content revision is independent of the application release.
RECIPE_RELEASE_VERSION = "0.2.0"


def pack(files):
    """Stable ZIP entry metadata; project IDs and check timestamps are still run-specific."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return stream.getvalue()


def project_inventory(files):
    files.pop("manifest.json", None)
    files["manifest.json"] = encoded(
        {
            "format": "storygal-project-inventory",
            "version": 1,
            "files": {name: digest(raw) for name, raw in sorted(files.items())},
        }
    )


def seed_bundle(app, recipe, public, files):
    """Construct the documented exchange format, then let normal import validate it.

    The bootstrap blank project supplies current default state shapes only. Published
    media IDs stay stable; dialogues are recovered by byte spans, not repeated text.
    """
    from storygal.bundles import FIELDS, Bundles
    from storygal.review import top_dialogues

    project = app.state.store.create(
        files["storygal-source/original.txt"], "赤壁.txt", "public_domain", "utf-8"
    )
    seed = read_zip(Bundles(app).export(project["id"]))
    document = json.loads(seed["project.json"])
    document["records"] = {name: [] for name in document["records"]}
    rows = document["records"]
    for cid, character in public["characters"].items():
        rows["characters"].append(
            {
                "id": cid,
                "display_name": character["name"],
                "aliases": recipe["characters"][cid]["aliases"],
                "description": recipe["characters"][cid]["description"],
                "evidence": [],
                "status": "confirmed",
                "active_figure_id": character["figure_id"],
                "origin": "public_release",
                "merged_into": None,
            }
        )
    runs = [r for b in public["blocks"] for r in b["runs"] if r["speaker_id"]]
    for dialogue in top_dialogues(files["storygal-source/source.utf8.txt"]):
        start, end = dialogue["byte_start"], dialogue["byte_end"]
        dialogue["id"] = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"{recipe['source_sha256']}:{start}:{end}")
        )
        speakers = {
            r["speaker_id"]
            for r in runs
            if r["byte_start"] <= start and r["byte_end"] >= end
        }
        if len(speakers) > 1:
            raise ValueError("公开阅读包对白存在归属冲突。")
        if speakers:
            dialogue.update(
                speaker_id=speakers.pop(),
                status="reviewed",
                reviewer="public-v0.1.0-record",
                reviewed_at=None,
                origin="public_release",
            )
        rows["dialogues"].append(dialogue)
    for asset in public["media"].values():
        table, directory = (
            ("assets", "assets")
            if asset["type"] == "figure"
            else ("reader_assets", "reader-assets")
        )
        record = {k: v for k, v in asset.items() if k in FIELDS[table].split()}
        # Do not trigger repository-specific sample import/export behavior.
        record["origin"] = "public_release"
        record["created_at"] = asset.get("created_at", "2026-11-12T00:00:00+08:00")
        rows[table].append(record)
        seed[f"{directory}/{asset['id']}.png"] = files[asset["url"][2:]]
    config = copy.deepcopy(public["config"])
    config["illustrations"] = []  # New plan application owns these twelve anchors.
    document["states"]["reader_states"] = {"revision": 0, "data": config}
    document["states"]["speech_states"] = {
        "revision": 0,
        "data": {"profiles": {}, "lines": {}},
    }
    document["review_revision"] = 0
    seed["project.json"] = encoded(document)
    project_inventory(seed)
    return pack(seed)


def call(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.is_error:
        raise ValueError(f"构建操作失败 {method} {path}: {response.text}")
    return response


def sync_reader_data(files, previous, content):
    """Support an optional inline data file without silently shipping two identities."""
    if "reader-data.js" not in files:
        return
    match = re.fullmatch(
        r"((?:window|globalThis)\.[A-Za-z_$][\w$]*\s*=\s*)(\{.*\});?\s*",
        files["reader-data.js"].decode(),
        re.DOTALL,
    )
    if not match or json.loads(match[2]) != previous:
        raise ValueError(
            "reader-data.js 格式未知或与 reader.json 不同，拒绝不完整身份迁移。"
        )
    files["reader-data.js"] = (
        match[1] + json.dumps(content, ensure_ascii=False) + ";\n"
    ).encode()


def public_reader(raw, recipe, review_raw, recipe_raw, old_files, public, maker_assets=None):
    files = read_zip(raw)
    verify_inventory(files)
    previous = json.loads(files["reader.json"])
    content = copy.deepcopy(previous)
    # Stable publication identity is deliberately independent of local import IDs.
    content["project"]["id"] = recipe["public_work_id"]
    old_plates = {p["id"]: p for p in public["config"]["illustrations"]}
    for plate in content["config"]["illustrations"]:
        old_id = plate["id"].removeprefix("plan-")
        if old_id not in old_plates or any(
            plate[k] != old_plates[old_id][k]
            for k in ("after_byte", "image_asset_id", "title")
        ):
            raise ValueError("新插图与旧书签位置无法一一对应。")
        plate["id"] = old_id
    if (
        content["characters"] != public["characters"]
        or content["presentations"] != public["presentations"]
        or content["map"] != public["map"]
        or content["map_entries"] != public["map_entries"]
        or set(content["media"]) != set(public["media"])
        or content["blocks"] != public["blocks"]
    ):
        raise ValueError("重建改变了人物、正文片段、55段编排、地图或媒体集合。")
    for aid, asset in content["media"].items():
        if (
            asset["type"] == "audio"
            or asset["sha256"] != public["media"][aid]["sha256"]
            or files[asset["url"][2:]] != old_files[public["media"][aid]["url"][2:]]
        ):
            raise ValueError("重建改变了公开图片或引入音频。")
    files["reader.json"] = encoded(content)
    sync_reader_data(files, previous, content)
    # Provenance travels from the verified public input, not untracked local sample files.
    files.update(
        {n: b for n, b in old_files.items() if n.startswith("storygal-source/")}
    )
    files["storygal-source/chibi-rebuild-v0.2.0.json"] = recipe_raw
    files["storygal-source/chibi-visual-review-v0.2.0.json"] = review_raw
    files.update(maker_assets or {})
    files["licenses/Taleprism-MIT.txt"] = (ROOT / "LICENSE").read_bytes()
    files["SHOWCASE.txt"] = (
        f"Taleprism v{VERSION} 赤壁主示例：12幅插图、8角色、9立绘、55呈现、3阶段地图。\n"
        "从固定哈希的v0.1.0公开阅读包重建，制作方案含9场景与12镜头。"
        "原文与全部图片未改；不含系统语音及任何音频配置。\n"
        "助手逐图检查及局限见storygal-source/chibi-visual-review-v0.2.0.json；"
        "最终创作者美术复核仍为pending。\n"
        "制作侧追溯及成对检查见storygal-source/examples/chibi/；"
        "当前火船旗色连续性needs_revision，统一旗色仅为后续建议，未修改图片。\n"
        "公开作品ID与旧插图ID保留，继续使用同一浏览器、同一站点时可沿用阅读记录。\n"
    ).encode()
    inventory = json.loads(files.pop("storygal-delivery.json"))
    inventory["files"] = {
        n: {"bytes": len(b), "sha256": digest(b)} for n, b in sorted(files.items())
    }
    files["storygal-delivery.json"] = encoded(inventory)
    verify_inventory(files)
    return pack(files)


def rebuild(recipe, review, files, public, recipe_raw, review_raw, maker_assets=None):
    from fastapi.testclient import TestClient
    from storygal.bundles import Bundles
    from storygal.production import Plan

    # Catch malformed plans before opening a workbench. Passing reviews are created only
    # by the production API after exact recipe/source/image checks in preflight.
    plan = Plan.model_validate(recipe["plan"]).model_dump()
    if len(plan["scenes"]) != recipe["expected"]["scenes"] or any(
        s["status"] != "draft" or s["continuity_check"] for s in plan["shots"]
    ):
        raise ValueError("配方须保留草稿方案与独立的实际检查记录。")
    with tempfile.TemporaryDirectory(prefix="taleprism-chibi-public-") as temporary:
        root = Path(temporary)
        # app.py owns a module-level app. Redirect that initialization too, and restore
        # the caller's environment afterward. Never read .env or contact a service.
        with (
            patch.dict(os.environ, {"STORYGAL_DATA_DIR": str(root / "initial")}),
            patch("storygal.settings.load_env"),
        ):
            app_module = importlib.import_module("storygal.app")
            with patch.object(app_module, "load_env"):
                app = app_module.create_app(root / "build")
                with TestClient(app) as client:
                    response = call(
                        client,
                        "POST",
                        "/api/project-bundles",
                        files={
                            "file": (
                                "chibi-bootstrap.zip",
                                seed_bundle(app, recipe, public, files),
                            )
                        },
                    )
                    pid = response.json()["id"]
                    if response.json().get("restore_issues"):
                        raise ValueError("公开内容恢复存在待修复项。")
                    production, reader = app.state.production, app.state.reader
                    production.save(pid, 0, recipe["source_sha256"], plan)
                    prefix = f"/api/projects/{pid}"
                    for shot in sorted(plan["shots"], key=lambda s: s["after_byte"]):
                        call(
                            client,
                            "POST",
                            prefix + "/production/" + shot["id"] + "/approve",
                            json={"revision": production.load(pid)[0]},
                        )
                    for shot in sorted(plan["shots"], key=lambda s: s["after_byte"]):
                        call(
                            client,
                            "POST",
                            prefix + "/production/" + shot["id"] + "/continuity-check",
                            json={
                                "revision": production.load(pid)[0],
                                "decision": "passed",
                                "reviewer": "assistant",
                                "notes": f"依据2026-11-12逐图记录 SHA256 {digest(review_raw)}。"
                                + review["shots"][shot["id"]]
                                + " 创作者最终复核仍待完成。",
                            },
                        )
                    production.apply(pid, production.load(pid)[0], reader.load(pid)[0])
                    checked = production.load(pid)[1]
                    if not all(
                        s["continuity_check"]["status"] == "passed"
                        for s in checked["shots"]
                    ):
                        raise ValueError("制作检查未全部生效。")
                    if app.state.delivery.state(pid)["records"]:
                        raise ValueError("不得生成最终创作者复核。")
                    project_raw = Bundles(app).export(pid)
                    project_files = read_zip(project_raw)
                    document = json.loads(project_files["project.json"])
                    if document["records"]["speech_takes"] or document["states"][
                        "speech_states"
                    ]["data"] != {"profiles": {}, "lines": {}}:
                        raise ValueError("公开工程不得保留声音资产或配置。")
                    project_files["README.txt"] += (
                        "\n公开来源："
                        + recipe["source_archive"]["url"]
                        + "\n源包SHA256："
                        + recipe["source_archive"]["sha256"]
                        + "\n以下记录为助手实际看图后的制作检查，创作者最终复核pending。\n"
                    ).encode() + review_raw
                    if maker_assets:
                        # The project exchange intentionally admits no arbitrary extra files.
                        # Carry a readable maker supplement in README, preserving its schema.
                        project_files["README.txt"] += (
                            "\n\n制作追溯补充：历史逐图prompt、v0.2事后配方、通用模板是不同材料。"
                            "当前三图旗色成对检查needs_revision；共享青色仅为未来修订建议，"
                            "未修改图片，创作者最终检查pending。完整追溯随独立阅读包"
                            "storygal-source/examples/chibi/及源码提供。\n\n"
                        ).encode()
                        for name in (GUIDE, TRACE, GATE):
                            project_files["README.txt"] += (
                                "\n=== " + name + " ===\n"
                            ).encode() + maker_assets["storygal-source/" + name]
                    project_inventory(project_files)
                    project_raw = pack(project_files)
                    # Exercise a clean import before returning a public editable artifact.
                    second = app_module.create_app(root / "roundtrip")
                    with TestClient(second) as other:
                        restored = call(
                            other,
                            "POST",
                            "/api/project-bundles",
                            files={"file": ("chibi-project.zip", project_raw)},
                        ).json()
                        new_id = restored["id"]
                        if new_id == pid or restored.get("restore_issues"):
                            raise ValueError("公开工程跨工作台恢复失败。")
                        if second.state.production.load(new_id)[1] != checked:
                            raise ValueError("公开工程恢复改变了镜头检查状态。")
                        export = call(
                            other, "POST", f"/api/projects/{new_id}/reader/exports"
                        ).json()
                        job = next(
                            j
                            for j in second.state.store.jobs(new_id)
                            if j["id"] == export["job_id"]
                        )
                        if job["state"] != "completed":
                            raise ValueError(job.get("error", "阅读包导出未完成"))
                        reader_raw = call(
                            other, "GET", job["result"]["download_url"]
                        ).content
                    reader_raw = public_reader(
                        reader_raw, recipe, review_raw, recipe_raw, files, public, maker_assets
                    )
                    return project_raw, reader_raw


def build(source, output):
    source, output = Path(source), Path(output)
    for legacy in (
        ROOT / ".release/chibi-demo",
        ROOT / ".release/v0.1.0",
        ROOT / ".release/v0.2.0",
        ROOT / ".release/v0.2.0-chibi",
    ):
        if output.resolve().is_relative_to(legacy.resolve()):
            raise ValueError("请使用新的发布输出目录，不能覆盖历史发布产物。")
    recipe, review, files, public, recipe_raw, review_raw = preflight(
        source, RECIPE, REVIEW
    )
    if recipe["release_version"] != RECIPE_RELEASE_VERSION:
        raise ValueError("赤壁配方不是当前构建器支持的已检查内容版本。")
    maker_assets = provenance_assets(files, public)
    project_raw, reader_raw = rebuild(
        recipe, review, files, public, recipe_raw, review_raw, maker_assets
    )
    results = {
        f"{PREFIX}-chibi-project.zip": project_raw,
        f"{PREFIX}-chibi-reader.zip": reader_raw,
    }
    artifacts = [
        {
            "file": n,
            "bytes": len(b),
            "sha256": digest(b),
            "example": "chibi",
            "kind": "project" if n.endswith("-project.zip") else "reader",
        }
        for n, b in results.items()
    ]
    reader_item = next(a for a in artifacts if a["kind"] == "reader")
    record = {
        "version": VERSION,
        "artifacts": artifacts,
        **{k: reader_item[k] for k in ("file", "bytes", "sha256")},
        "source_archive": recipe["source_archive"],
        "source_sha256": recipe["source_sha256"],
        "recipe_sha256": digest(recipe_raw),
        "visual_review_sha256": digest(review_raw),
        **recipe["expected"],
        "public_work_id": recipe["public_work_id"],
        "system_audio_included": False,
        "production_reviewer": "assistant",
        "creator_final_art_review": "pending",
        "maker_trace_sha256": digest(maker_assets["storygal-source/" + TRACE]),
        "paired_shot_continuity": "needs_revision",
        "paired_shot_record_sha256": digest(maker_assets["storygal-source/" + GATE]),
        "flag_correction_applied": False,
        "checks": {
            "public_input_inventory": True,
            "source_bytes_unchanged": True,
            "all_27_image_bytes_unchanged": True,
            "production_checks": 12,
            "clean_project_roundtrip": True,
            "reader_export_after_import": True,
            "public_work_id_preserved": True,
            "legacy_illustration_ids_preserved": True,
            "no_audio_assets_or_profiles": True,
            "browser": "not_run",
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    # Freeze only complete artifacts; the manifest is the last published local file.
    for name, raw in results.items():
        temporary = output / (name + ".partial")
        temporary.write_bytes(raw)
        temporary.replace(output / name)
    (output / "chibi-demo-manifest.json").write_bytes(encoded(record))
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="下载后保存在本机的固定v0.1.0赤壁公开阅读包；脚本不联网。",
    )
    parser.add_argument("--output", type=Path, default=ROOT / (".release/v" + VERSION + "-chibi"))
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), ensure_ascii=False, indent=2))
