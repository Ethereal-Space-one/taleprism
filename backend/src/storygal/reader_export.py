import hashlib
import json
import shutil
import stat
import zipfile

from .exporter import assert_versions, copy_verified, include_project_license, published_fields
from .llm import api_key
from .portable_reader import TEMPLATE, embed_story
from .production import Production
from .reader import REPO


def file_hash(path):
    # Do not allocate the entire reader ZIP just to publish a content digest.
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def read_runtime(build):
    """Capture a single verified pair; rebuilding the frontend cannot ship a partial JS/CSS file."""
    try:
        checks = json.loads((build / "runtime-checksums.json").read_text("utf-8"))
        names = ("reader.js", "reader.css")
        if not isinstance(checks, dict) or set(checks) != set(names):
            raise ValueError()
        assets = {name: (build / name).read_bytes() for name in names}
        if any(
            not raw or hashlib.sha256(raw).hexdigest() != checks[name]
            for name, raw in assets.items()
        ):
            raise ValueError()
        return assets
    except (OSError, ValueError):
        raise ValueError(
            "独立阅读器构建缺失、不完整或正在更新。请完成 ./start.sh 构建后重新导出；之前的成品未变。"
        ) from None


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
    # An explicit null is important: unlike an absent motion key it cannot
    # trigger a legacy sample effect. Leave the editable configuration intact.
    if "illustrations" in content["config"]:
        plates = []
        for plate in content["config"]["illustrations"]:
            motion = plate.get("motion")
            if motion:
                projection = None
                if motion["reviewed"] is True:
                    # The full author recipe was validated against source and image
                    # above. The player needs geometry and binding, not personal notes.
                    geometry = {
                        "rain-wet-ground": "areas ground drops rings",
                        "wave-impact-backwash": "water bank hits",
                    }[motion["effect"]]
                    projection = published_fields(
                        motion,
                        "version effect image_sha256 source_sha256 after_byte width height reviewed "
                        + geometry,
                    ) | {"playback_only": True}
                plate = plate | {"motion": projection}
            plates.append(plate)
        content["config"] = content["config"] | {"illustrations": plates}
    # The database's accepted TTS take still contains its private voice/profile
    # directions and cache key. Attach playback bytes/credits, not that record.
    content["media"] = {
        aid: published_fields(
            asset,
            "id type sha256 duration origin credit"
            if asset["type"] == "audio"
            else "id type sha256 width height origin license label portrait_state sample_key",
        )
        for aid, asset in content["media"].items()
    }
    versions = content["versions"]
    dist = REPO / "frontend/dist"
    reader_build = dist / "reader"
    runtime = read_runtime(reader_build)
    parent = store.project_dir(pid) / "exports"
    parent.mkdir(exist_ok=True)
    staging, target = parent / (jid + ".partial"), parent / jid
    zip_staging, archive = parent / (jid + ".zip.partial"), parent / (jid + ".zip")
    try:
        staging.mkdir()
        (staging / "assets").mkdir()
        for name, raw in runtime.items():
            (staging / "assets" / name).write_bytes(raw)
        (staging / "media").mkdir()
        for aid, asset in content["media"].items():
            if asset.get("origin") == "paragraph_narration" and asset["type"] == "audio":
                source, ext = reader.narrations.path(pid, aid), ".wav"
            elif asset.get("origin") == "paragraph_soundscape" and asset["type"] == "audio":
                source, ext = reader.soundscapes.path(pid, aid), ".wav"
            elif asset["type"] == "audio":
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
        (staging / "index.html").write_text(embed_story(TEMPLATE, content), encoding="utf-8")
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
        include_project_license(REPO, staging)
        for module in ["react", "react-dom", "scheduler"]:
            module_dir = REPO / "frontend/node_modules" / module
            license_path = next(
                (
                    p
                    for p in module_dir.glob("*")
                    if p.name.lower() in {"license", "license.md", "license.txt"}
                ),
                None,
            )
            if not license_path:
                raise ValueError(f"缺少 {module} 许可文件；请重新安装前端依赖后导出。")
            shutil.copy2(license_path, licenses / (module + ".txt"))
        # The classic reader always includes search (OpenCC code + dictionary).
        opencc_dir = REPO / "frontend/node_modules/opencc-js"
        for name, target_name in [
            ("LICENSE", "opencc-js.txt"),
            ("THIRD_PARTY_LICENSES.md", "opencc-js-THIRD_PARTY_LICENSES.md"),
            ("LICENSES/Apache-2.0.txt", "opencc-js-Apache-2.0.txt"),
        ]:
            if not (opencc_dir / name).is_file():
                raise ValueError(f"缺少 opencc-js 许可文件 {name}；请重新安装前端依赖后导出。")
            shutil.copy2(opencc_dir / name, licenses / target_name)
        paragraph_credits = list(
            dict.fromkeys(
                m["credit"]
                for m in content["media"].values()
                if m.get("origin") == "paragraph_narration" and m.get("credit")
            )
        )
        (staging / "RIGHTS.txt").write_text(
            "原文权利状态："
            + content["project"]["rights_status"]
            + "\n素材来源见 reader.json；生图提示词如适用在 storygal-source。\n"
            + (
                "历史地图为约略阅读示意，进一步考据与用户最终审核尚待完成。\n"
                if content.get("map")
                else ""
            )
            + (
                "\n段落朗读来源与许可：\n" + "\n".join(paragraph_credits) + "\n\n"
                if paragraph_credits
                else ""
            )
            + (
                "段落声景：由 Taleprism 在本机按创作选择生成，不是现场录音、音乐或朗读。\n"
                if any(m.get("origin") == "paragraph_soundscape" for m in content["media"].values())
                else ""
            )
            + "完整性检查不授予额外使用权或证明历史事实。\n"
            + "Taleprism 阅读器代码：licenses/Taleprism-MIT.txt；第三方依赖保留各自许可。\n",
            encoding="utf-8",
        )
        (staging / "README.txt").write_text(
            "Taleprism · 独立阅读器 / Offline reader\n\n"
            "1. 完整解压 ZIP（不要在压缩包、网盘或邮件预览中打开）。\n"
            "2. 双击 index.html，用桌面浏览器阅读。不需要联网、终端、Python 或制作台，关闭网页即结束。\n"
            "3. 分享时发送整个 ZIP；单发 HTML 会缺少 assets 中的程序和 media 中的原图、声音。\n\n"
            "Extract the entire ZIP, then double-click index.html in a desktop browser. No server, "
            "installation, or internet connection is required. Keep the folders together; share the ZIP, "
            "not just the HTML file.\n"
            "Reader software: licenses/Taleprism-MIT.txt. This does not license the manuscript or media; "
            "see RIGHTS.txt for content and licenses/ for the bundled dependencies.\n\n"
            "封面保持安静。「开始阅读」后，读到作者安排的位置，已采用的声景响一次，插图依原文出现；"
            "只有已复核的动效会动。采用的回声折页在后段展开。静图始终是静图；减少动态效果时不播动效。\n"
            "可在封面选「安静阅读」，或用「暂停」暂停自动演绎；「静音」将全部声音关闭。"
            "若浏览器拦住第一次声音，点「开启声音」即可。段落朗读须主动点播；对白配音由独立设置控制。\n"
            "Start reading to follow the author’s sound, imagery and echo at their passages. "
            "Stills stay still; reduced motion prevents animation. Choose Quiet reading for manual cues, "
            "pause automatic effects, or mute all audio. If your browser blocks sound, tap the reader’s prompt. "
            "Narration is on demand; dialogue has separate controls. No model runs when you read.\n"
            "缺失图片或声音时仍可读正文；请重新完整解压原 ZIP 修复素材。\n"
            "进度和书签只保存在当前浏览器；本地文件的记录可能随浏览器、隐私设置或移动目录而变化，"
            "不会同步到其他地址或设备。\n\n"
            "备用打开方式：若浏览器或设备策略限制本地网页，可请提供者托管同一目录，"
            "或在已安装 Python 3.9+ 的 macOS 双击「打开阅读器.command」；用「停止阅读器.command」结束服务。"
            "启动器仅绑定本机，关闭网页不会停服；停止服务后再移动阅读包，不要更改系统安全设置。\n"
            "可选完整性检查：使用 Python 在解压目录运行 python3 verify_package.py；双击 HTML 不执行此检查。"
            "手动本机服务：python3 -m http.server 8080 --bind 127.0.0.1，然后打开 http://127.0.0.1:8080。\n"
            "原文在 storygal-source；素材和地图来源见 reader.json 与 RIGHTS.txt。继续创作需另存可编辑工程 ZIP。\n",
            encoding="utf-8",
        )
        shutil.copy2(REPO / "tools/verify_package.py", staging / "verify_package.py")
        shutil.copy2(REPO / "tools/reader_launcher.py", staging / "reader_launcher.py")
        for name in ("打开阅读器.command", "停止阅读器.command"):
            shutil.copy2(REPO / "tools/reader_launcher.command", staging / name)
            (staging / name).chmod(0o755)
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
                    "sha256": file_hash(p),
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
                    if p.suffix == ".command":
                        # Preserve Finder executability even when exporting on Windows.
                        info = zipfile.ZipInfo.from_file(p, p.relative_to(staging))
                        info.create_system = 3
                        info.external_attr = (stat.S_IFREG | 0o755) << 16
                        z.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
                    else:
                        z.write(p, p.relative_to(staging))
        with zipfile.ZipFile(zip_staging) as z:
            if z.testzip() is not None or set(z.namelist()) != set(inventory["files"]) | {
                "storygal-delivery.json"
            }:
                raise ValueError("阅读器压缩包校验失败，请重试。")
        digest = file_hash(zip_staging)
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
