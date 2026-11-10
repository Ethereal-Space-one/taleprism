import json
import shutil
import zipfile

from .exporter import assert_versions, copy_verified
from .llm import api_key
from .production import Production
from .reader import REPO
from .text import sha256


def export_reader(reader, pid, jid):
    store = reader.store
    content = reader.content(pid, strict=True)
    # A compiled plan illustration still depends on the production checks that approved it.
    content["versions"]["production_revision"] = Production(reader).validate_applied(
        pid, content["config"]
    )
    # Deliberate publication contract: internal notes and personal browser records never travel.
    content = {
        key: content[key]
        for key in [
            "schema_version",
            "project",
            "versions",
            "config",
            "blocks",
            "characters",
            "media",
            "map",
            "preview",
            "issues",
            "presentations",
            "map_entries",
        ]
    }
    versions = content["versions"]
    dist = REPO / "frontend/dist"
    if not (dist / "index.html").is_file():
        raise ValueError("缺少阅读器构建，请重新运行启动程序。")
    parent = store.project_dir(pid) / "exports"
    parent.mkdir(exist_ok=True)
    staging, target = parent / (jid + ".partial"), parent / jid
    zip_staging, archive = parent / (jid + ".zip.partial"), parent / (jid + ".zip")
    try:
        staging.mkdir()
        shutil.copytree(dist / "assets", staging / "assets")
        html = (dist / "index.html").read_text().replace('"/assets/', '"./assets/')
        html = html.replace(
            "<head>", '<head><meta name="storygal-reader-export" content="./reader.json">'
        )
        (staging / "index.html").write_text(html, encoding="utf-8")
        (staging / "media").mkdir()
        for aid, asset in content["media"].items():
            if asset["type"] == "audio":
                source, ext = reader.speech.path(pid, asset), ".wav"
            elif asset["type"] == "figure":
                source, ext = reader.review.asset_path(pid, aid), ".png"
            else:
                source, ext = reader.path(pid, aid), ".png"
            copy_verified(source, staging / "media" / (aid + ext), asset["sha256"])
            asset["url"] = "./media/" + aid + ext
        content["preview"] = False
        (staging / "reader.json").write_text(
            json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        sources = staging / "storygal-source"
        sources.mkdir()
        shutil.copy2(store.project_dir(pid) / "original.txt", sources / "original.txt")
        shutil.copy2(store.project_dir(pid) / "source.utf8.txt", sources / "source.utf8.txt")
        if any(
            a.get("origin") == "codex_imagegen" and a["type"] == "image"
            for a in content["media"].values()
        ):
            for name in ["prompts.json", "PROVENANCE.md"]:
                shutil.copy2(REPO / "samples/reader" / name, sources / name)
        if any(
            a.get("origin") == "codex_imagegen" and a["type"] == "figure"
            for a in content["media"].values()
        ):
            portrait_sources = sources / "characters"
            portrait_sources.mkdir()
            for name in ["prompts.json", "README.md"]:
                shutil.copy2(REPO / "samples/characters" / name, portrait_sources / name)
            if any(
                a.get("sample_key") in {"caocao", "guanyu", "lusu", "huanggai", "zhouyu_ill"}
                for a in content["media"].values()
            ):
                expansion_sources = portrait_sources / "expansion-v1"
                expansion_sources.mkdir()
                for name in ["prompts.json", "PROVENANCE.md"]:
                    shutil.copy2(
                        REPO / "samples/characters/expansion-v1" / name, expansion_sources / name
                    )
            if any(
                a.get("sample_key") in {"zhaoyun", "zhangfei"} for a in content["media"].values()
            ):
                second_sources = portrait_sources / "expansion-v2"
                second_sources.mkdir()
                for name in ["prompts.json", "PROVENANCE.md"]:
                    shutil.copy2(
                        REPO / "samples/characters/expansion-v2" / name, second_sources / name
                    )
        licenses = staging / "licenses"
        if any(
            (a.get("sample_key") or "").startswith("narrative:") for a in content["media"].values()
        ):
            narrative_sources = sources / "narrative-v1"
            narrative_sources.mkdir()
            for name in ["prompts.json", "PROVENANCE.md"]:
                shutil.copy2(REPO / "samples/reader/narrative-v1" / name, narrative_sources / name)
        licenses.mkdir()
        for module in [
            "react",
            "react-dom",
            "scheduler",
            "@tanstack/react-query",
            "@tanstack/query-core",
        ]:
            module_dir = REPO / "frontend/node_modules" / module
            license_path = next(
                (
                    p
                    for p in module_dir.glob("*")
                    if p.name.lower() in {"license", "license.md", "license.txt"}
                ),
                None,
            )
            if license_path:
                shutil.copy2(license_path, licenses / (module.replace("/", "-") + ".txt"))
        (staging / "RIGHTS.txt").write_text(
            "原文权利状态："
            + content["project"]["rights_status"]
            + "\n图像、语音、地图的来源与说明见 reader.json；生图提示词如适用在 storygal-source。\n历史地图为约略阅读示意，进一步考据与用户最终审核尚待完成。\n完整性检查不授予额外使用权或证明历史事实。\n前端依赖许可证见 licenses。\n",
            encoding="utf-8",
        )
        (staging / "README.txt").write_text(
            "Taleprism · 视觉小说阅读器\n\n先运行 python3 verify_package.py，再运行 python3 -m http.server 8080 --bind 127.0.0.1\n打开 http://127.0.0.1:8080，不能直接双击 HTML。\n\n正文连续阅读，场景随原文位置切换。声音仅覆盖已制作的部分对白，需主动开启；目录、搜索和收藏可临时查阅，再返回阅读处。地图可自由对照阶段，标明正文所在阶段。\n进度和字号只保存在当前浏览器；不向制作台或分析服务发送阅读进度，不同步到其他设备。\n原文保存在 storygal-source；素材与地图来源见 reader.json。\n本包为成品快照，继续编辑请另存制作台的可编辑工程 ZIP。\n",
            encoding="utf-8",
        )
        shutil.copy2(REPO / "tools/verify_package.py", staging / "verify_package.py")
        secret = api_key().encode()
        if secret and any(secret in p.read_bytes() for p in staging.rglob("*") if p.is_file()):
            raise ValueError("导出物包含本机服务密钥，已停止打包。")
        inventory = {
            "schema_version": 1,
            "export_id": jid,
            "versions": versions,
            "files": {
                p.relative_to(staging).as_posix(): {
                    "bytes": p.stat().st_size,
                    "sha256": sha256(p.read_bytes()),
                }
                for p in sorted(staging.rglob("*"))
                if p.is_file()
            },
        }
        (staging / "storygal-delivery.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with zipfile.ZipFile(zip_staging, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(staging.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(staging))
        with zipfile.ZipFile(zip_staging) as z:
            if z.testzip() is not None or set(z.namelist()) != set(inventory["files"]) | {
                "storygal-delivery.json"
            }:
                raise ValueError("阅读器压缩包校验失败，请重试。")
        digest = sha256(zip_staging.read_bytes())
        store.verify(pid)
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            assert_versions(db, pid, versions)
            zip_staging.rename(archive)
            staging.rename(target)
        return {
            "export_id": jid,
            "format": "reader",
            **versions,
            "archive_sha256": digest,
            "file_count": len(inventory["files"]),
            "play_url": f"/play/{pid}/{jid}/index.html",
            "download_url": f"/api/projects/{pid}/exports/{jid}/download",
            "checks": {
                "source": True,
                "paragraph_text": True,
                "assets": True,
                "render": "not_run",
                "no_service_keys": True,
            },
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(target, ignore_errors=True)
        zip_staging.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        raise
